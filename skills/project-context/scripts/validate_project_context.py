#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_context_index import (  # noqa: E402
    FRONTMATTER_RE,
    INDEX_END_MARKER,
    INDEX_START_MARKER,
    extract_context_index,
    parse_frontmatter,
    render_context_index,
)
from project_context_markdown import iter_inline_link_targets  # noqa: E402
from project_context_structure import (  # noqa: E402
    MAX_MULTI_PAGE_PRIMARY_BODY_CHARS,
    MAX_SINGLE_PAGE_BODY_CHARS,
    assess_primary_structure,
)


DEFAULT_DOC = "docs/project-context.md"
DEFAULT_DOC_DIR = "docs/project-context"
DEFAULT_METADATA = "docs/project-context/.metadata.json"
TEMP_PLAN = "docs/project-context/_plan.md"
CURRENT_GENERATOR_VERSION = "20"
SNAPSHOT_EXCLUDED_PATHS = {DEFAULT_METADATA, TEMP_PLAN}
MAX_INITIAL_DOCS = 8
SMALL_REPO_SOURCE_FILE_LIMIT = 10
SMALL_REPO_DOC_LIMIT = 3
MIN_SUBPAGE_BODY_CHARS = 500
MIN_SINGLE_FILE_SECTION_CHARS = 1500
SOURCE_COMMIT_RE = re.compile(r"^source_commit:\s*([A-Za-z0-9._/-]+)\s*$", re.MULTILINE)
UPDATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
PROJECT_CONTEXT_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
EVIDENCE_HEADING_RE = re.compile(r"^##\s+근거\s*$", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
COMMIT_HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
HOST_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w:/.-])(?:/[Uu]sers|/home|/private|/var/folders)/[^\s)`>]+")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|password|passwd|credential)\b\s*[:=]\s*['\"]?"
    r"(?!<|\$|\{|\[|your-|example|placeholder|redacted|xxx|todo|none|null|false|true)"
    r"[A-Za-z0-9_./+=:@-]{12,}"
)
PRIMARY_DOC_SECTION_PATTERNS = {
    "repository overview": re.compile(
        r"^##\s+(?:프로젝트\s*(?:요약|개요)|Repository Overview|Overview)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "change guidance": re.compile(
        r"^##\s+(?:작업\s*(?:전\s*)?(?:확인|주의|가이드)(?:\s*지점)?|Change Guidance|Working Notes|Agent Notes)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "testing guidance": re.compile(
        r"^##\s+(?:검증\s*방법|테스트|Testing|Validation|Checks?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "workflow/domain guidance": re.compile(
        r"^##\s+(?:주요\s*흐름|업무\s*흐름|도메인|비즈니스|제품\s*로직|"
        r"Workflows?|Business Logic|Product Logic|Domain(?: Concepts?)?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
}
CONTEXT_DOC_TEXT = "docs/project-context.md"
REPOSITORY_OVERVIEW_TEXT = "repository overview"
ARCHITECTURE_NOTES_TEXT = "architecture notes"
TESTING_GUIDANCE_TEXT = "testing guidance"
SOURCE_MAPS_TEXT = "source maps"
FOLLOW_LINKS_TEXT = "follow its links"
CODE_DISCOVERY_TEXT = "code discovery"
ORDINARY_PROJECT_QUESTIONS_TEXT = "ordinary project questions"
DO_NOT_PRELOAD_TEXT = "do not preload every supporting page"
READ_WHEN_TEXT = "read_when"
EXACT_IMPLEMENTATION_VERIFICATION_TEXT = "exact implementation verification"
CURRENT_SOURCE_AUTHORITATIVE_TEXT = "current source remains authoritative"
SKILL_TRIGGER_TEXT = "$project-context"
WRITE_AUTHORITY_TEXT = "missing or stale context alone does not authorize writes"
AGENT_START_MARKER = "<!-- project-context:start -->"
AGENT_END_MARKER = "<!-- project-context:end -->"
PRIMARY_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".gradle",
    ".graphql",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".m",
    ".mm",
    ".php",
    ".proto",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}
PRIMARY_SOURCE_NAMES = {
    "Dockerfile",
    "Makefile",
    "justfile",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
}
IGNORED_SOURCE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.lock",
    "go.sum",
}


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


def git_commit_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "--no-pager", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return False
    return result.returncode == 0


def git_tracked_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "--no-pager", "ls-files", "-z"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


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
    for raw_target in iter_inline_link_targets(markdown):
        target = clean_target(raw_target)
        if not target or is_external_target(target) or target.startswith("/"):
            continue
        yield target


def iter_markdown_links(markdown: str):
    for raw_target in iter_inline_link_targets(markdown):
        target = clean_target(raw_target)
        if target:
            yield target


def discover_docs(root: Path, primary_doc: str) -> list[str]:
    docs = [primary_doc]
    doc_dir = root / DEFAULT_DOC_DIR
    if doc_dir.exists() and not doc_dir.is_symlink() and doc_dir.is_dir():
        for path in sorted(doc_dir.rglob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in docs:
                docs.append(rel)
    return docs


def collect_doc_sources(root: Path, docs: list[str]) -> dict[str, list[str]]:
    source_map: dict[str, list[str]] = {}
    for doc in docs:
        doc_path = root / doc
        if doc_path.is_symlink() or not doc_path.is_file():
            source_map[doc] = []
            continue
        sources: list[str] = []
        markdown = doc_path.read_text(encoding="utf-8", errors="replace")
        for link in iter_relative_links(markdown):
            target_path = (doc_path.parent / link).resolve()
            try:
                rel = target_path.relative_to(root).as_posix()
            except ValueError:
                continue
            if is_context_doc_rel(rel) or rel in sources:
                continue
            sources.append(rel)
        source_map[doc] = sources
    return source_map


def read_json(path: Path) -> tuple[dict | None, str | None]:
    if path.is_symlink():
        return None, "metadata must not be a symlink"
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


def validate_repo_relative_path(label: str, value: str) -> str | None:
    path = Path(value)
    if value.strip() == "":
        return f"{label} must not be empty"
    if path.is_absolute():
        return f"{label} must be relative to the repository root: {value}"
    if ".." in path.parts:
        return f"{label} must not contain parent directory traversal: {value}"
    return None


def symlink_parent(root: Path, rel_path: str) -> str | None:
    current = root
    for part in Path(rel_path).parent.parts:
        current = current / part
        if current.is_symlink():
            return current.relative_to(root).as_posix()
    return None


def validate_repo_path(root: Path, label: str, value: str) -> str | None:
    path_error = validate_repo_relative_path(label, value)
    if path_error:
        return path_error
    symlink = symlink_parent(root, value)
    if symlink:
        return f"{label} parent must not be a symlink: {symlink}"
    return None


def is_expected_snapshot_race_error(error: OSError) -> bool:
    return isinstance(error, (FileNotFoundError, IsADirectoryError, NotADirectoryError)) or error.errno in {
        errno.EISDIR,
        errno.ENOENT,
        errno.ENOTDIR,
    }


def snapshot_file_bytes(path: Path) -> bytes | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_bytes()
    except OSError:
        return None


def docs_content_hash(root: Path, docs: list[str]) -> str:
    digest = hashlib.sha256()
    seen_files: set[str] = set()

    def add_file(rel: str, path: Path) -> None:
        if rel in seen_files or rel in SNAPSHOT_EXCLUDED_PATHS:
            return
        content = snapshot_file_bytes(path)
        if content is None:
            return
        seen_files.add(rel)
        digest.update(f"file:{rel}".encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")

    def add_directory(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as error:
            if is_expected_snapshot_race_error(error):
                digest.update("missing".encode("utf-8"))
                return
            raise
        for path in entries:
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel in SNAPSHOT_EXCLUDED_PATHS or path.is_symlink():
                continue
            try:
                if path.is_dir():
                    digest.update(f"dir:{rel}".encode("utf-8"))
                    digest.update(b"\0")
                    add_directory(path)
                elif path.is_file():
                    add_file(rel, path)
            except OSError as error:
                if is_expected_snapshot_race_error(error):
                    continue
                raise

    primary_doc = docs[0] if docs else DEFAULT_DOC
    primary_path = root / primary_doc
    if primary_path.is_file():
        add_file(primary_doc, primary_path)

    doc_dir = root / DEFAULT_DOC_DIR
    if doc_dir.exists() and not doc_dir.is_symlink() and doc_dir.is_dir():
        add_directory(doc_dir)
    return digest.hexdigest()


def is_context_doc_rel(path: str) -> bool:
    return path == DEFAULT_DOC or path.startswith(f"{DEFAULT_DOC_DIR}/")


def is_primary_source_file(path: str) -> bool:
    if is_context_doc_rel(path):
        return False
    name = Path(path).name
    if name in IGNORED_SOURCE_NAMES:
        return False
    if name in PRIMARY_SOURCE_NAMES:
        return True
    return Path(path).suffix in PRIMARY_SOURCE_SUFFIXES


def count_primary_source_files(root: Path) -> int:
    return sum(1 for path in git_tracked_files(root) if is_primary_source_file(path))


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
    raw_doc_path = root / doc_rel
    if raw_doc_path.is_symlink():
        return [f"document must not be a symlink: {doc_rel}"], warnings
    if not raw_doc_path.exists():
        return [f"missing document: {doc_rel}"], warnings
    if not raw_doc_path.is_file():
        return [f"document is not a file: {doc_rel}"], warnings

    doc_path = raw_doc_path.resolve()
    markdown = doc_path.read_text(encoding="utf-8", errors="replace")
    body = FRONTMATTER_RE.sub("", markdown).strip()
    frontmatter = parse_frontmatter(markdown)
    absolute_links = [
        link
        for link in iter_markdown_links(markdown)
        if link.startswith("/") and not is_external_target(link)
    ]
    for link in absolute_links:
        errors.append(f"{doc_rel}: absolute link path is not allowed: {link}")
    for match in HOST_ABSOLUTE_PATH_RE.finditer(markdown):
        errors.append(f"{doc_rel}: host absolute path is not allowed: {match.group(0)}")
    if PRIVATE_KEY_RE.search(markdown):
        errors.append(f"{doc_rel}: private key material is not allowed")
    if AWS_ACCESS_KEY_RE.search(markdown):
        errors.append(f"{doc_rel}: secret-looking AWS access key is not allowed")
    if SECRET_ASSIGNMENT_RE.search(markdown):
        errors.append(f"{doc_rel}: secret-looking assignment value is not allowed")

    commit_hashes = set(COMMIT_HASH_RE.findall(body))
    if len(commit_hashes) >= 3:
        warnings.append(f"{doc_rel}: persistent commit hash list suspected; keep git evidence in update metadata or temporary plan")

    if require_metadata:
        if not frontmatter:
            errors.append(f"{doc_rel}: missing YAML frontmatter metadata")
        if frontmatter.get("generated_by") != "project-context":
            errors.append(f"{doc_rel}: missing metadata: generated_by: project-context")
        updated_at = frontmatter.get("updated_at")
        if not updated_at or not UPDATED_AT_RE.match(updated_at):
            errors.append(f"{doc_rel}: missing metadata: updated_at ISO-8601 timestamp")
        mode = frontmatter.get("mode")
        if mode not in {"single-page", "multi-page"}:
            errors.append(f"{doc_rel}: missing metadata: mode single-page|multi-page")

    source_commit_match = SOURCE_COMMIT_RE.search(markdown)
    if require_metadata and not source_commit_match:
        errors.append(f"{doc_rel}: missing metadata: source_commit")
    if source_commit_match:
        source_commit = source_commit_match.group(1)
        resolved_commit = git_resolve_commit(root, source_commit)
        if not resolved_commit:
            errors.append(f"{doc_rel}: source_commit does not exist in git: {source_commit}")

    evidence_section = extract_evidence_section(markdown)
    if not evidence_section:
        errors.append(f"{doc_rel}: missing section: ## 근거")

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
    if doc_rel == DEFAULT_DOC:
        section_patterns = PRIMARY_DOC_SECTION_PATTERNS
        if frontmatter.get("mode") == "multi-page":
            section_patterns = {
                name: pattern
                for name, pattern in PRIMARY_DOC_SECTION_PATTERNS.items()
                if name in {"repository overview", "change guidance"}
            }
        for section_name, pattern in section_patterns.items():
            if not pattern.search(markdown):
                warnings.append(f"{doc_rel}: primary doc should include {section_name} section")

    return errors, warnings


def validate_metadata(root: Path, docs: list[str], primary_doc: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    metadata_path = root / DEFAULT_METADATA
    if metadata_path.is_symlink():
        errors.append(f"update metadata must not be a symlink: {DEFAULT_METADATA}")
        return errors, warnings
    if not metadata_path.exists():
        errors.append(f"missing update metadata: {DEFAULT_METADATA}")
        return errors, warnings
    if not metadata_path.is_file():
        errors.append(f"update metadata is not a file: {DEFAULT_METADATA}")
        return errors, warnings

    metadata, read_error = read_json(metadata_path)
    if metadata is None:
        errors.append(f"invalid update metadata: {DEFAULT_METADATA}: {read_error}")
        return errors, warnings

    if metadata.get("generator") != "project-context":
        errors.append(f"{DEFAULT_METADATA}: generator must be project-context")
    generator_version = metadata.get("generator_version")
    if not isinstance(generator_version, str) or not generator_version.strip():
        errors.append(f"{DEFAULT_METADATA}: missing generator_version")
    updated_at = metadata.get("updated_at")
    if not isinstance(updated_at, str) or not PROJECT_CONTEXT_TIMESTAMP_RE.match(updated_at):
        errors.append(f"{DEFAULT_METADATA}: updated_at must be a UTC millisecond timestamp")
    run_mode = metadata.get("run_mode")
    if run_mode not in {"init", "update"}:
        errors.append(f"{DEFAULT_METADATA}: run_mode must be init or update")

    primary_doc_ref = metadata.get("primary_doc")
    if primary_doc_ref != primary_doc:
        errors.append(f"{DEFAULT_METADATA}: primary_doc must be {primary_doc}")

    source_commit_ref = metadata.get("source_commit")
    resolved_source_commit = None
    if not isinstance(source_commit_ref, str) or not source_commit_ref.strip():
        errors.append(f"{DEFAULT_METADATA}: source_commit must be a non-empty string")
    else:
        resolved_source_commit = git_resolve_commit(root, source_commit_ref.strip())
        if not resolved_source_commit:
            errors.append(f"{DEFAULT_METADATA}: source_commit does not exist in git: {source_commit_ref.strip()}")

    source_commit_short = metadata.get("source_commit_short")
    if not isinstance(source_commit_short, str) or not source_commit_short.strip():
        errors.append(f"{DEFAULT_METADATA}: source_commit_short must be a non-empty string")
    else:
        resolved_source_commit_short = git_resolve_commit(root, source_commit_short.strip())
        if not resolved_source_commit_short:
            errors.append(f"{DEFAULT_METADATA}: source_commit_short does not exist in git: {source_commit_short.strip()}")
        elif resolved_source_commit and resolved_source_commit_short != resolved_source_commit:
            errors.append(f"{DEFAULT_METADATA}: source_commit_short must resolve to source_commit")

    reviewed_commit_ref = metadata.get("reviewed_commit")
    resolved_reviewed_commit = None
    if "reviewed_commit" not in metadata:
        message = f"{DEFAULT_METADATA}: missing reviewed_commit; run project_context_update.py record"
        if generator_version == "18":
            warnings.append(message)
        else:
            errors.append(message)
    elif not isinstance(reviewed_commit_ref, str) or not reviewed_commit_ref.strip():
        errors.append(f"{DEFAULT_METADATA}: reviewed_commit must be a non-empty string")
    else:
        resolved_reviewed_commit = git_resolve_commit(root, reviewed_commit_ref.strip())
        if not resolved_reviewed_commit:
            errors.append(f"{DEFAULT_METADATA}: reviewed_commit does not exist in git: {reviewed_commit_ref.strip()}")
        elif resolved_source_commit and (
            not git_commit_is_ancestor(root, resolved_source_commit, resolved_reviewed_commit)
            or not git_commit_is_ancestor(root, resolved_reviewed_commit, "HEAD")
        ):
            errors.append(
                f"{DEFAULT_METADATA}: reviewed_commit must be between source_commit and HEAD"
            )

    primary_path = root / primary_doc
    if resolved_source_commit and primary_path.is_file() and not primary_path.is_symlink():
        primary_markdown = primary_path.read_text(encoding="utf-8", errors="replace")
        source_commit_match = SOURCE_COMMIT_RE.search(primary_markdown)
        if source_commit_match:
            doc_source_commit = source_commit_match.group(1)
            resolved_doc_source_commit = git_resolve_commit(root, doc_source_commit)
            if resolved_doc_source_commit and resolved_doc_source_commit != resolved_source_commit:
                errors.append(
                    f"{DEFAULT_METADATA}: source_commit does not match {primary_doc}: "
                    f"{source_commit_ref.strip()} != {doc_source_commit}"
                )

    content_hash = metadata.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash.strip():
        errors.append(f"{DEFAULT_METADATA}: missing content_hash")
    else:
        current_hash = docs_content_hash(root, docs)
        if content_hash != current_hash:
            errors.append(f"{DEFAULT_METADATA}: content_hash mismatch; run project_context_update.py record after valid docs changes")

    recorded_docs = metadata.get("docs")
    if isinstance(recorded_docs, list) and all(isinstance(doc, str) for doc in recorded_docs):
        if sorted(recorded_docs) != sorted(docs):
            errors.append(f"{DEFAULT_METADATA}: docs list does not match current context documents")
    else:
        errors.append(f"{DEFAULT_METADATA}: docs must be a string list")

    doc_sources = metadata.get("doc_sources")
    if not isinstance(doc_sources, dict) or not all(
        isinstance(doc, str)
        and isinstance(sources, list)
        and all(isinstance(source, str) for source in sources)
        for doc, sources in doc_sources.items()
    ):
        errors.append(f"{DEFAULT_METADATA}: doc_sources must map document paths to source path lists")
    elif sorted(doc_sources) != sorted(docs):
        errors.append(f"{DEFAULT_METADATA}: doc_sources keys must match current context documents")
    else:
        expected_doc_sources = collect_doc_sources(root, docs)
        normalized_actual = {doc: sorted(set(sources)) for doc, sources in doc_sources.items()}
        normalized_expected = {
            doc: sorted(set(sources)) for doc, sources in expected_doc_sources.items()
        }
        if normalized_actual != normalized_expected:
            errors.append(f"{DEFAULT_METADATA}: doc_sources do not match current document source links")

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


def validate_deterministic_context_index(
    root: Path,
    doc_rel: str,
    docs: list[str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    primary_path = root / doc_rel
    if primary_path.is_symlink() or not primary_path.is_file():
        return errors, warnings
    markdown = primary_path.read_text(encoding="utf-8", errors="replace")
    mode = parse_frontmatter(markdown).get("mode")
    if mode != "multi-page":
        if INDEX_START_MARKER in markdown or INDEX_END_MARKER in markdown:
            warnings.append(f"{doc_rel}: single-page document should not contain context index markers")
        return errors, warnings

    current_index, marker_errors = extract_context_index(markdown)
    errors.extend(f"{doc_rel}: {error}" for error in marker_errors)
    expected_index, metadata_errors = render_context_index(root, doc_rel, docs)
    errors.extend(metadata_errors)
    if current_index is not None and expected_index is not None and current_index != expected_index:
        errors.append(f"{doc_rel}: deterministic context index is stale; run project_context_update.py sync-index")
    return errors, warnings


def validate_context_relationships(root: Path, doc_rel: str, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    subdocs = [doc for doc in docs if doc != doc_rel]
    if len(subdocs) < 3:
        return errors, warnings

    subdoc_set = set(subdocs)
    related_subdocs: set[str] = set()
    for subdoc in subdocs:
        subdoc_path = root / subdoc
        if subdoc_path.is_symlink() or not subdoc_path.is_file():
            continue
        markdown = subdoc_path.read_text(encoding="utf-8", errors="replace")
        for link in iter_relative_links(markdown):
            target_path = (subdoc_path.parent / link).resolve()
            try:
                target = target_path.relative_to(root).as_posix()
            except ValueError:
                continue
            if target in subdoc_set and target != subdoc:
                related_subdocs.update((subdoc, target))

    for subdoc in sorted(subdoc_set - related_subdocs):
        warnings.append(
            f"{subdoc}: isolated from peer context pages; add an evidence-backed relationship link, "
            "merge it, or review whether it is intentionally standalone"
        )
    return errors, warnings


def validate_primary_mode(root: Path, doc_rel: str, docs: list[str]) -> tuple[list[str], list[str]]:
    issues = assess_primary_structure(root, doc_rel, docs)
    errors = [
        f"{issue['path']}: {issue['message']}"
        for issue in issues
        if issue["code"] == "primary-mode-mismatch"
    ]
    return errors, []


def validate_primary_size(root: Path, doc_rel: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for issue in assess_primary_structure(root, doc_rel, [doc_rel]):
        if issue["code"] == "multi-page-primary-too-large":
            errors.append(
                f"{doc_rel}: multi-page primary body has {issue['body_chars']} characters; "
                f"keep the router at or below {MAX_MULTI_PAGE_PRIMARY_BODY_CHARS}"
            )
        elif issue["code"] == "single-page-primary-too-large":
            warnings.append(
                f"{doc_rel}: single-page body has {issue['body_chars']} characters; "
                f"split into indexed supporting pages above {MAX_SINGLE_PAGE_BODY_CHARS}"
            )
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


def marked_agent_section(text: str) -> str | None:
    start = text.find(AGENT_START_MARKER)
    end = text.find(AGENT_END_MARKER)
    if start == -1 or end == -1 or start > end:
        return None
    return text[start : end + len(AGENT_END_MARKER)]


def is_semantically_current_agent_section(section: str) -> bool:
    return (
        CONTEXT_DOC_TEXT in section
        and REPOSITORY_OVERVIEW_TEXT in section
        and ARCHITECTURE_NOTES_TEXT in section
        and TESTING_GUIDANCE_TEXT in section
        and SOURCE_MAPS_TEXT in section
        and FOLLOW_LINKS_TEXT in section
        and CODE_DISCOVERY_TEXT in section
        and ORDINARY_PROJECT_QUESTIONS_TEXT in section
        and DO_NOT_PRELOAD_TEXT in section
        and READ_WHEN_TEXT in section
        and EXACT_IMPLEMENTATION_VERIFICATION_TEXT in section
        and CURRENT_SOURCE_AUTHORITATIVE_TEXT in section
        and SKILL_TRIGGER_TEXT in section
        and WRITE_AUTHORITY_TEXT in section
    )


def validate(root: Path, doc_rel: str) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    temp_plan_path = root / TEMP_PLAN
    if temp_plan_path.exists() or temp_plan_path.is_symlink():
        errors.append(f"temporary plan must be deleted before finish: {TEMP_PLAN}")
    if (root / DEFAULT_DOC_DIR).is_symlink():
        errors.append(f"context doc directory must not be a symlink: {DEFAULT_DOC_DIR}")
    docs = discover_docs(root, doc_rel)
    docs = [doc for doc in docs if doc != TEMP_PLAN]
    metadata_errors, metadata_warnings = validate_metadata(root, docs, doc_rel)
    errors.extend(metadata_errors)
    warnings.extend(metadata_warnings)
    if len(docs) > MAX_INITIAL_DOCS:
        warnings.append(f"many context docs: {len(docs)}; initial runs usually stay at {MAX_INITIAL_DOCS} or fewer")
    primary_source_count = count_primary_source_files(root)
    if 0 < primary_source_count <= SMALL_REPO_SOURCE_FILE_LIMIT and len(docs) > SMALL_REPO_DOC_LIMIT:
        warnings.append(
            f"small repo with {primary_source_count} primary source file(s): prefer {DEFAULT_DOC} plus at most 1-2 supporting pages"
        )
    for index, doc in enumerate(docs):
        doc_errors, doc_warnings = validate_doc(root, doc, require_metadata=index == 0)
        errors.extend(doc_errors)
        warnings.extend(doc_warnings)
    index_errors, index_warnings = validate_index_links(root, doc_rel, docs)
    errors.extend(index_errors)
    warnings.extend(index_warnings)
    deterministic_index_errors, deterministic_index_warnings = validate_deterministic_context_index(
        root, doc_rel, docs
    )
    errors.extend(deterministic_index_errors)
    warnings.extend(deterministic_index_warnings)
    relationship_errors, relationship_warnings = validate_context_relationships(root, doc_rel, docs)
    errors.extend(relationship_errors)
    warnings.extend(relationship_warnings)
    mode_errors, mode_warnings = validate_primary_mode(root, doc_rel, docs)
    errors.extend(mode_errors)
    warnings.extend(mode_warnings)
    size_errors, size_warnings = validate_primary_size(root, doc_rel)
    errors.extend(size_errors)
    warnings.extend(size_warnings)
    section_errors, section_warnings = validate_section_directories(root, docs)
    errors.extend(section_errors)
    warnings.extend(section_warnings)

    agent_files = ("AGENTS.md", "CLAUDE.md")
    existing_agent_files = [
        agent_file
        for agent_file in agent_files
        if (root / agent_file).exists() or (root / agent_file).is_symlink()
    ]
    if not existing_agent_files:
        errors.append("missing AGENTS.md or CLAUDE.md project context reference")

    for agent_file in existing_agent_files:
        agent_path = root / agent_file
        if agent_path.is_symlink():
            errors.append(f"{agent_file} must not be a symlink")
            continue
        if not agent_path.is_file():
            errors.append(f"{agent_file} is not a file")
            continue
        agent_text = agent_path.read_text(encoding="utf-8", errors="replace")
        start_count = agent_text.count(AGENT_START_MARKER)
        end_count = agent_text.count(AGENT_END_MARKER)
        if CONTEXT_DOC_TEXT not in agent_text:
            errors.append(f"{agent_file} does not mention {CONTEXT_DOC_TEXT}")
        if start_count != 1 or end_count != 1:
            errors.append(f"{agent_file} project context reference must have exactly one marked section")
        marked_section = marked_agent_section(agent_text)
        if marked_section is None:
            errors.append(f"{agent_file} project context marker section is malformed")
        elif not is_semantically_current_agent_section(marked_section):
            errors.append(f"{agent_file} project context reference is stale; run project_context_agents.py")
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
    doc_error = validate_repo_path(root, "--doc", args.doc)
    if doc_error:
        print(doc_error, file=sys.stderr)
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
