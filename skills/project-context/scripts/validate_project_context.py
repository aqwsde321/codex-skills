#!/usr/bin/env python3
import argparse
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
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SOURCE_COMMIT_RE = re.compile(r"^source_commit:\s*([A-Za-z0-9._/-]+)\s*$", re.MULTILINE)
EVIDENCE_HEADING_RE = re.compile(r"^##\s+근거\s*$", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
CONTEXT_DOC_TEXT = "docs/project-context.md"
AGENT_START_MARKER = "<!-- project-context:start -->"
AGENT_END_MARKER = "<!-- project-context:end -->"


def git_short_head(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


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


def discover_docs(root: Path, primary_doc: str) -> list[str]:
    docs = [primary_doc]
    doc_dir = root / DEFAULT_DOC_DIR
    if doc_dir.exists() and doc_dir.is_dir():
        for path in sorted(doc_dir.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            if rel not in docs:
                docs.append(rel)
    return docs


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


def validate(root: Path, doc_rel: str) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if (root / TEMP_PLAN).exists():
        errors.append(f"temporary plan must be deleted before finish: {TEMP_PLAN}")
    docs = discover_docs(root, doc_rel)
    docs = [doc for doc in docs if doc != TEMP_PLAN]
    if len(docs) > MAX_INITIAL_DOCS:
        warnings.append(f"many context docs: {len(docs)}; initial OpenWiki-style runs usually stay at {MAX_INITIAL_DOCS} or fewer")
    for index, doc in enumerate(docs):
        doc_errors, doc_warnings = validate_doc(root, doc, require_metadata=index == 0)
        errors.extend(doc_errors)
        warnings.extend(doc_warnings)

    for agent_file in ("AGENTS.md", "CLAUDE.md"):
        agent_path = root / agent_file
        if not agent_path.exists():
            if agent_file == "AGENTS.md":
                warnings.append("missing AGENTS.md project context reference")
            continue
        if not agent_path.is_file():
            warnings.append(f"{agent_file} is not a file")
            continue
        agent_text = agent_path.read_text(encoding="utf-8", errors="replace")
        if CONTEXT_DOC_TEXT not in agent_text:
            warnings.append(f"{agent_file} does not mention {CONTEXT_DOC_TEXT}")
        elif AGENT_START_MARKER not in agent_text or AGENT_END_MARKER not in agent_text:
            warnings.append(f"{agent_file} project context reference is unmarked")

    metadata_path = root / DEFAULT_METADATA
    if not metadata_path.exists():
        warnings.append(f"missing update metadata: {DEFAULT_METADATA}")

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
