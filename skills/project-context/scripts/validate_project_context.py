#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


DEFAULT_DOC = "docs/project-context.md"
DEFAULT_DOC_DIR = "docs/project-context"
DEFAULT_METADATA = "docs/project-context/.metadata.json"
TEMP_PLAN = "docs/project-context/_plan.md"
MAX_INITIAL_DOCS = 8
MIN_SUBPAGE_BODY_CHARS = 500
MIN_SINGLE_FILE_SECTION_CHARS = 1500
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SOURCE_COMMIT_RE = re.compile(r"^source_commit:\s*([A-Za-z0-9._/-]+)\s*$", re.MULTILINE)
EVIDENCE_HEADING_RE = re.compile(r"^##\s+근거\s*$", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
COMMIT_HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
VOLATILE_FRONTMATTER_RE = re.compile(r"^(source_commit|updated_at|updatedAt):\s*.*$", re.MULTILINE)
CONTEXT_DOC_TEXT = "docs/project-context.md"
AGENT_START_MARKER = "<!-- project-context:start -->"
AGENT_END_MARKER = "<!-- project-context:end -->"


def git_output(root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def git_commit_exists(root: Path, ref: str) -> bool:
    return git_resolve_commit(root, ref) is not None


def git_resolve_commit(root: Path, ref: str) -> str | None:
    return git_output(root, ["rev-parse", "--verify", f"{ref}^{{commit}}"])


def git_short_head(root: Path) -> str | None:
    return git_output(root, ["rev-parse", "--short", "HEAD"])


def git_full_head(root: Path) -> str | None:
    return git_output(root, ["rev-parse", "HEAD"])


def is_external_target(target: str) -> bool:
    lowered = target.lower()
    return (
        "://" in lowered
        or lowered.startswith("#")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    )


def clean_target(target: str) -> str:
    target = target.strip()
    target = target.split("#", 1)[0]
    target = target.split("?", 1)[0]
    return unquote(target).strip()


def iter_relative_links(markdown: str):
    for match in LINK_RE.finditer(markdown):
        target = clean_target(match.group(1))
        if not target or is_external_target(target) or target.startswith("/"):
            continue
        yield target


def iter_markdown_links(markdown: str):
    for match in LINK_RE.finditer(markdown):
        target = clean_target(match.group(1))
        if target:
            yield target


def discover_docs(root: Path, primary_doc: str) -> list[str]:
    docs = [primary_doc]
    doc_dir = root / DEFAULT_DOC_DIR
    if doc_dir.exists() and doc_dir.is_dir():
        for path in sorted(doc_dir.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            if rel not in docs:
                docs.append(rel)
    return docs


def read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except OSError as error:
        return None, str(error)
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error.msg}"
    if not isinstance(value, dict):
        return None, "metadata root must be an object"
    return value, None


def stable_doc_bytes(path: Path) -> bytes:
    markdown = path.read_text(encoding="utf-8", errors="replace")
    if not markdown.startswith("---\n"):
        return markdown.encode("utf-8")
    lines = markdown.splitlines(keepends=True)
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return markdown.encode("utf-8")
    frontmatter = "".join(lines[1:end_index])
    stable_frontmatter = VOLATILE_FRONTMATTER_RE.sub("", frontmatter)
    stable = "".join([lines[0], stable_frontmatter, *lines[end_index:]])
    return stable.encode("utf-8")


def docs_content_hash(root: Path, docs: list[str]) -> str:
    digest = hashlib.sha256()
    for doc in docs:
        path = root / doc
        if not path.exists() or not path.is_file():
            continue
        digest.update(doc.encode("utf-8"))
        digest.update(b"\0")
        digest.update(stable_doc_bytes(path))
        digest.update(b"\0")
    return digest.hexdigest()


def is_context_doc_rel(path: str) -> bool:
    return path == DEFAULT_DOC or path.startswith(f"{DEFAULT_DOC_DIR}/")


def extract_evidence_section(markdown: str) -> str:
    match = EVIDENCE_HEADING_RE.search(markdown)
    if not match:
        return ""
    start = match.end()
    next_heading = NEXT_H2_RE.search(markdown, start)
    end = next_heading.start() if next_heading else len(markdown)
    return markdown[start:end]


def validate_doc(root: Path, doc_rel: str, require_metadata: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    doc_path = (root / doc_rel).resolve()
    if not doc_path.exists():
        return [f"missing document: {doc_rel}"], warnings
    if not doc_path.is_file():
        return [f"document is not a file: {doc_rel}"], warnings

    markdown = doc_path.read_text(encoding="utf-8", errors="replace")
    body = FRONTMATTER_RE.sub("", markdown).strip()
    absolute_links = [
        link
        for link in iter_markdown_links(markdown)
        if link.startswith("/") and not is_external_target(link)
    ]
    for link in absolute_links:
        errors.append(f"{doc_rel}: absolute link path is not allowed: {link}")

    commit_hashes = set(COMMIT_HASH_RE.findall(body))
    if len(commit_hashes) >= 3:
        warnings.append(f"{doc_rel}: persistent commit hash list suspected; keep git evidence in update metadata or temporary plan")

    source_commit_match = SOURCE_COMMIT_RE.search(markdown)
    if require_metadata and not source_commit_match:
        errors.append(f"{doc_rel}: missing metadata: source_commit")

    evidence_section = extract_evidence_section(markdown)
    if not evidence_section:
        errors.append(f"{doc_rel}: missing section: ## 근거")

    head = git_short_head(root)
    if source_commit_match and head:
        source_commit = source_commit_match.group(1)
        if source_commit != head:
            warnings.append(f"{doc_rel}: stale source_commit: {source_commit} != {head}")

    links = list(iter_relative_links(markdown))
    evidence_links = set(iter_relative_links(evidence_section))
    if not links:
        errors.append(f"{doc_rel}: missing relative source links")

    broken_links: list[str] = []
    links_to_index = False
    evidence_source_links: list[str] = []
    doc_dir = doc_path.parent
    index_path = (root / DEFAULT_DOC).resolve()
    for link in links:
        target_path = (doc_dir / link).resolve()
        if target_path == index_path:
            links_to_index = True
        try:
            target_path.relative_to(root)
        except ValueError:
            broken_links.append(f"{link} -> outside repo")
            continue
        if not target_path.exists():
            broken_links.append(link)
            continue
        if link in evidence_links:
            rel = target_path.relative_to(root).as_posix()
            if not is_context_doc_rel(rel):
                evidence_source_links.append(rel)

    for link in broken_links:
        errors.append(f"{doc_rel}: broken source link: {link}")

    if doc_rel.startswith(f"{DEFAULT_DOC_DIR}/") and not links_to_index:
        errors.append(f"{doc_rel}: missing link back to {DEFAULT_DOC}")

    if evidence_section and not evidence_source_links:
        errors.append(f"{doc_rel}: missing source evidence links in ## 근거")

    if doc_rel.startswith(f"{DEFAULT_DOC_DIR}/") and doc_rel != TEMP_PLAN and len(body) < MIN_SUBPAGE_BODY_CHARS:
        warnings.append(f"{doc_rel}: thin page; merge into {DEFAULT_DOC} or expand with source-grounded guidance")

    return errors, warnings


def validate_metadata(root: Path, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    metadata_path = root / DEFAULT_METADATA
    if not metadata_path.exists():
        warnings.append(f"missing update metadata: {DEFAULT_METADATA}")
        return errors, warnings
    if not metadata_path.is_file():
        errors.append(f"update metadata is not a file: {DEFAULT_METADATA}")
        return errors, warnings

    metadata, read_error = read_json(metadata_path)
    if metadata is None:
        errors.append(f"invalid update metadata: {DEFAULT_METADATA}: {read_error}")
        return errors, warnings

    for key in ("updatedAt", "command", "model"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{DEFAULT_METADATA}: missing OpenWiki metadata field: {key}")

    command = metadata.get("command")
    if isinstance(command, str) and command.strip() and command not in {"init", "update"}:
        warnings.append(f"{DEFAULT_METADATA}: unexpected command: {command}")

    commit_ref = metadata.get("source_commit") or metadata.get("gitHead")
    if not isinstance(commit_ref, str) or not commit_ref.strip():
        errors.append(f"{DEFAULT_METADATA}: missing source_commit or gitHead")
    else:
        commit_ref = commit_ref.strip()
        resolved_commit = git_resolve_commit(root, commit_ref)
        if not resolved_commit:
            errors.append(f"{DEFAULT_METADATA}: source commit does not exist in git: {commit_ref}")
        else:
            head = git_full_head(root)
            if head and resolved_commit != head:
                warnings.append(f"{DEFAULT_METADATA}: stale source commit: {resolved_commit} != {head}")

    content_hash = metadata.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash.strip():
        warnings.append(f"{DEFAULT_METADATA}: missing content_hash")
    else:
        current_hash = docs_content_hash(root, docs)
        if content_hash != current_hash:
            warnings.append(f"{DEFAULT_METADATA}: content_hash mismatch; run project_context_update.py record after valid docs changes")

    recorded_docs = metadata.get("docs")
    if isinstance(recorded_docs, list) and all(isinstance(doc, str) for doc in recorded_docs):
        if sorted(recorded_docs) != sorted(docs):
            warnings.append(f"{DEFAULT_METADATA}: docs list does not match current context documents")
    elif recorded_docs is not None:
        warnings.append(f"{DEFAULT_METADATA}: docs must be a string list")

    return errors, warnings


def validate_index_links(root: Path, doc_rel: str, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    primary_path = root / doc_rel
    if not primary_path.exists() or not primary_path.is_file():
        return errors, warnings
    subdocs = [doc for doc in docs if doc != doc_rel]
    if not subdocs:
        return errors, warnings

    markdown = primary_path.read_text(encoding="utf-8", errors="replace")
    linked_targets = set()
    for link in iter_relative_links(markdown):
        target_path = (primary_path.parent / link).resolve()
        try:
            linked_targets.add(target_path.relative_to(root).as_posix())
        except ValueError:
            continue

    for subdoc in subdocs:
        if subdoc not in linked_targets:
            errors.append(f"{doc_rel}: missing index link to context page: {subdoc}")

    return errors, warnings


def doc_body_length(root: Path, doc_rel: str) -> int:
    path = root / doc_rel
    if not path.exists() or not path.is_file():
        return 0
    markdown = path.read_text(encoding="utf-8", errors="replace")
    return len(FRONTMATTER_RE.sub("", markdown).strip())


def validate_section_directories(root: Path, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    section_docs: dict[str, list[str]] = {}
    for doc in docs:
        if not doc.startswith(f"{DEFAULT_DOC_DIR}/"):
            continue
        remainder = doc[len(DEFAULT_DOC_DIR) + 1 :]
        if "/" not in remainder:
            continue
        section = remainder.split("/", 1)[0]
        section_docs.setdefault(section, []).append(doc)

    for section, section_doc_list in sorted(section_docs.items()):
        if len(section_doc_list) == 1:
            doc = section_doc_list[0]
            body_length = doc_body_length(root, doc)
            if body_length < MIN_SINGLE_FILE_SECTION_CHARS:
                warnings.append(
                    f"{DEFAULT_DOC_DIR}/{section}/: single-file section directory; prefer a broader page or heading unless this boundary is substantial"
                )

    return errors, warnings


def validate(root: Path, doc_rel: str) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if (root / TEMP_PLAN).exists():
        errors.append(f"temporary plan must be deleted before finish: {TEMP_PLAN}")
    docs = discover_docs(root, doc_rel)
    docs = [doc for doc in docs if doc != TEMP_PLAN]
    metadata_errors, metadata_warnings = validate_metadata(root, docs)
    errors.extend(metadata_errors)
    warnings.extend(metadata_warnings)
    if len(docs) > MAX_INITIAL_DOCS:
        warnings.append(f"many context docs: {len(docs)}; initial OpenWiki-style runs usually stay at {MAX_INITIAL_DOCS} or fewer")
    for index, doc in enumerate(docs):
        doc_errors, doc_warnings = validate_doc(root, doc, require_metadata=index == 0)
        errors.extend(doc_errors)
        warnings.extend(doc_warnings)
    index_errors, index_warnings = validate_index_links(root, doc_rel, docs)
    errors.extend(index_errors)
    warnings.extend(index_warnings)
    section_errors, section_warnings = validate_section_directories(root, docs)
    errors.extend(section_errors)
    warnings.extend(section_warnings)

    agent_files = ("AGENTS.md", "CLAUDE.md")
    existing_agent_files = [agent_file for agent_file in agent_files if (root / agent_file).exists()]
    if not existing_agent_files:
        warnings.append("missing AGENTS.md or CLAUDE.md project context reference")

    for agent_file in existing_agent_files:
        agent_path = root / agent_file
        if not agent_path.is_file():
            warnings.append(f"{agent_file} is not a file")
            continue
        agent_text = agent_path.read_text(encoding="utf-8", errors="replace")
        if CONTEXT_DOC_TEXT not in agent_text:
            warnings.append(f"{agent_file} does not mention {CONTEXT_DOC_TEXT}")
        elif AGENT_START_MARKER not in agent_text or AGENT_END_MARKER not in agent_text:
            warnings.append(f"{agent_file} project context reference is unmarked")

    if errors:
        return 1, errors, warnings
    return 0, [f"project context valid: {len(docs)} document(s)"], warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Codex-native project context docs.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root.")
    parser.add_argument("--doc", default=DEFAULT_DOC, help=f"Document path relative to repo root. Default: {DEFAULT_DOC}")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"repo root is not a directory: {root}", file=sys.stderr)
        return 2

    code, messages, warnings = validate(root, args.doc)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    stream = sys.stderr if code else sys.stdout
    for message in messages:
        print(message, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
