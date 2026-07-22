#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_context_index import (  # noqa: E402
    AREA_INDEX_GENERATOR,
    CONCEPT_FIELD_LIMITS,
    FRONTMATTER_RE,
    INDEX_FIELD_LIMITS,
    INDEX_END_MARKER,
    INDEX_START_MARKER,
    area_index_for_concept,
    extract_context_index,
    parse_frontmatter,
    render_context_indexes,
    wiki_inventory,
)
from project_context_markdown import iter_inline_link_targets  # noqa: E402
from project_context_graph import (  # noqa: E402
    collect_semantic_relationships,
    page_content_hashes,
)
from project_context_safety import (  # noqa: E402
    canonical_commit_oid,
    context_tree_symlinks,
    require_git_repository,
    resolve_commit_oid,
    symlink_parent,
)
from project_context_structure import (  # noqa: E402
    MAX_MULTI_PAGE_PRIMARY_BODY_CHARS,
    MAX_SINGLE_PAGE_BODY_CHARS,
    assess_primary_structure,
)


DEFAULT_DOC = "docs/project-context.md"
DEFAULT_DOC_DIR = "docs/project-context"
DEFAULT_METADATA = "docs/project-context/.metadata.json"
TEMP_PLAN = "docs/project-context/_plan.md"
CURRENT_GENERATOR_VERSION = "21"
CURRENT_SCHEMA_VERSION = 2
SNAPSHOT_EXCLUDED_PATHS = {DEFAULT_METADATA, TEMP_PLAN}
MIN_SUBPAGE_BODY_CHARS = 500
UPDATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
PROJECT_CONTEXT_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
EVIDENCE_HEADING_RE = re.compile(r"^##\s+근거\s*$", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
COMMIT_HASH_RE = re.compile(r"\b[0-9a-f]{7,64}\b")
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


def git_resolve_commit(root: Path, ref: str) -> str | None:
    return resolve_commit_oid(root, ref)


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
    is_primary = doc_rel == DEFAULT_DOC
    is_area_index = doc_rel.startswith(f"{DEFAULT_DOC_DIR}/") and Path(doc_rel).name == "index.md"
    is_concept = (
        doc_rel.startswith(f"{DEFAULT_DOC_DIR}/")
        and doc_rel != TEMP_PLAN
        and not is_area_index
    )
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

    if is_area_index:
        if frontmatter.get("generated_by") != AREA_INDEX_GENERATOR:
            errors.append(
                f"{doc_rel}: missing metadata: generated_by: {AREA_INDEX_GENERATOR}"
            )
        for field in INDEX_FIELD_LIMITS:
            if not frontmatter.get(field, "").strip():
                errors.append(f"{doc_rel}: missing metadata: {field}")
    elif is_concept:
        for field in CONCEPT_FIELD_LIMITS:
            if not frontmatter.get(field, "").strip():
                errors.append(f"{doc_rel}: missing metadata: {field}")

    source_commit = frontmatter.get("source_commit", "").strip()
    if require_metadata and not source_commit:
        errors.append(f"{doc_rel}: missing metadata: source_commit")
    if source_commit:
        resolved_commit = git_resolve_commit(root, source_commit)
        if not resolved_commit:
            errors.append(f"{doc_rel}: source_commit does not exist in git: {source_commit}")
        elif canonical_commit_oid(root, source_commit) is None:
            errors.append(
                f"{doc_rel}: source_commit must be a canonical full commit ID: {source_commit}"
            )

    evidence_section = extract_evidence_section(markdown)
    if not is_area_index and not evidence_section:
        errors.append(f"{doc_rel}: missing section: ## 근거")

    links = list(iter_relative_links(markdown))
    evidence_links = set(iter_relative_links(evidence_section))
    if not is_area_index and not links:
        errors.append(f"{doc_rel}: missing relative source links")

    broken_links: list[str] = []
    evidence_source_links: list[str] = []
    doc_dir = doc_path.parent
    for link in links:
        target_path = (doc_dir / link).resolve()
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
        errors.append(f"{doc_rel}: broken link: {link}")

    if not is_area_index and evidence_section and not evidence_source_links:
        errors.append(f"{doc_rel}: missing source evidence links in ## 근거")

    if is_concept and len(body) < MIN_SUBPAGE_BODY_CHARS:
        warnings.append(
            f"{doc_rel}: thin page; verify it is a distinct concept with source-grounded guidance"
        )
    if is_primary:
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


def validate_metadata(
    root: Path,
    docs: list[str],
    primary_doc: str,
    metadata_override: dict | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    metadata_path = root / DEFAULT_METADATA
    if metadata_override is None:
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
    else:
        metadata = metadata_override

    if metadata.get("generator") != "project-context":
        errors.append(f"{DEFAULT_METADATA}: generator must be project-context")
    if metadata.get("schema_version") != CURRENT_SCHEMA_VERSION:
        errors.append(
            f"{DEFAULT_METADATA}: schema_version must be {CURRENT_SCHEMA_VERSION}; "
            "run project_context_update.py migrate --apply"
        )
    generator_version = metadata.get("generator_version")
    if not isinstance(generator_version, str) or not generator_version.strip():
        errors.append(f"{DEFAULT_METADATA}: missing generator_version")
    elif generator_version != CURRENT_GENERATOR_VERSION:
        errors.append(
            f"{DEFAULT_METADATA}: generator_version must be {CURRENT_GENERATOR_VERSION}"
        )
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
        elif canonical_commit_oid(root, source_commit_ref) is None:
            errors.append(
                f"{DEFAULT_METADATA}: source_commit must be a canonical full commit ID"
            )

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
        elif canonical_commit_oid(root, reviewed_commit_ref) is None:
            errors.append(
                f"{DEFAULT_METADATA}: reviewed_commit must be a canonical full commit ID"
            )
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
        doc_source_commit = parse_frontmatter(primary_markdown).get("source_commit", "").strip()
        if doc_source_commit:
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

    inventory = wiki_inventory(docs, primary_doc)
    expected_pages = list(inventory["pages"])
    expected_indexes = list(inventory["indexes"])
    recorded_pages = metadata.get("pages")
    if isinstance(recorded_pages, list) and all(isinstance(doc, str) for doc in recorded_pages):
        if sorted(recorded_pages) != sorted(expected_pages):
            errors.append(f"{DEFAULT_METADATA}: pages list does not match current context pages")
    else:
        errors.append(f"{DEFAULT_METADATA}: pages must be a string list")

    recorded_indexes = metadata.get("indexes")
    if isinstance(recorded_indexes, list) and all(isinstance(doc, str) for doc in recorded_indexes):
        if sorted(recorded_indexes) != sorted(expected_indexes):
            errors.append(f"{DEFAULT_METADATA}: indexes list does not match current area indexes")
    else:
        errors.append(f"{DEFAULT_METADATA}: indexes must be a string list")

    doc_sources = metadata.get("doc_sources")
    if not isinstance(doc_sources, dict) or not all(
        isinstance(doc, str)
        and isinstance(sources, list)
        and all(isinstance(source, str) for source in sources)
        for doc, sources in doc_sources.items()
    ):
        errors.append(f"{DEFAULT_METADATA}: doc_sources must map document paths to source path lists")
    elif sorted(doc_sources) != sorted(expected_pages):
        errors.append(f"{DEFAULT_METADATA}: doc_sources keys must match current context pages")
    else:
        expected_doc_sources = collect_doc_sources(root, expected_pages)
        normalized_actual = {doc: sorted(set(sources)) for doc, sources in doc_sources.items()}
        normalized_expected = {
            doc: sorted(set(sources)) for doc, sources in expected_doc_sources.items()
        }
        if normalized_actual != normalized_expected:
            errors.append(f"{DEFAULT_METADATA}: doc_sources do not match current document source links")

    doc_hashes = metadata.get("doc_hashes")
    if not isinstance(doc_hashes, dict) or not all(
        isinstance(page, str)
        and isinstance(content_hash, str)
        and re.fullmatch(r"[0-9a-f]{64}", content_hash)
        for page, content_hash in doc_hashes.items()
    ):
        errors.append(
            f"{DEFAULT_METADATA}: doc_hashes must map page paths to SHA-256 hashes"
        )
    elif sorted(doc_hashes) != sorted(expected_pages):
        errors.append(f"{DEFAULT_METADATA}: doc_hashes keys must match current context pages")
    elif doc_hashes != page_content_hashes(root, expected_pages):
        errors.append(
            f"{DEFAULT_METADATA}: doc_hashes do not match current context pages"
        )

    unmapped_resolutions = metadata.get("unmapped_resolutions")
    if not isinstance(unmapped_resolutions, list):
        errors.append(f"{DEFAULT_METADATA}: unmapped_resolutions must be a list")
    else:
        seen_resolution_paths: set[str] = set()
        for entry in unmapped_resolutions:
            if not isinstance(entry, dict):
                errors.append(
                    f"{DEFAULT_METADATA}: each unmapped resolution must be an object"
                )
                continue
            path = entry.get("path")
            resolution = entry.get("resolution")
            reason = entry.get("reason")
            if (
                not isinstance(path, str)
                or not path
                or path in seen_resolution_paths
                or resolution not in {"documented", "backlog", "ignored"}
                or not isinstance(reason, str)
                or (resolution in {"backlog", "ignored"} and not reason.strip())
            ):
                errors.append(
                    f"{DEFAULT_METADATA}: invalid unmapped resolution entry"
                )
                continue
            seen_resolution_paths.add(path)

    return errors, warnings


def validate_index_links(root: Path, doc_rel: str, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    inventory = wiki_inventory(docs, doc_rel)
    concepts = list(inventory["concepts"])
    owners = {
        doc_rel: list(inventory["indexes"]),
        **{
            index: [
                concept
                for concept in concepts
                if area_index_for_concept(concept) == index
            ]
            for index in inventory["indexes"]
        },
    }
    for owner, targets in owners.items():
        owner_path = root / owner
        if not owner_path.is_file() or owner_path.is_symlink():
            continue
        markdown = owner_path.read_text(encoding="utf-8", errors="replace")
        linked_targets = set()
        for link in iter_relative_links(markdown):
            target_path = (owner_path.parent / link).resolve()
            try:
                linked_targets.add(target_path.relative_to(root).as_posix())
            except ValueError:
                continue
        for target in targets:
            if target not in linked_targets:
                errors.append(f"{owner}: missing index link to context page: {target}")

    return errors, warnings


def validate_deterministic_context_index(
    root: Path,
    doc_rel: str,
    docs: list[str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    expected_indexes, metadata_errors = render_context_indexes(root, doc_rel, docs)
    errors.extend(metadata_errors)
    if expected_indexes is None:
        return errors, warnings
    if not expected_indexes:
        primary_path = root / doc_rel
        if primary_path.is_file() and not primary_path.is_symlink():
            markdown = primary_path.read_text(encoding="utf-8", errors="replace")
            if INDEX_START_MARKER in markdown or INDEX_END_MARKER in markdown:
                warnings.append(
                    f"{doc_rel}: home-only wiki should not contain context index markers"
                )
        return errors, warnings

    for index_doc, expected_index in expected_indexes.items():
        index_path = root / index_doc
        if index_path.is_symlink() or not index_path.is_file():
            continue
        markdown = index_path.read_text(encoding="utf-8", errors="replace")
        current_index, marker_errors = extract_context_index(markdown)
        errors.extend(f"{index_doc}: {error}" for error in marker_errors)
        if current_index is not None and current_index != expected_index:
            errors.append(
                f"{index_doc}: deterministic context index is stale; "
                "run project_context_update.py sync-index"
            )
    return errors, warnings


def validate_context_relationships(root: Path, doc_rel: str, docs: list[str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    inventory = wiki_inventory(docs, doc_rel, require_indexes=False)
    subdocs = list(inventory["concepts"])
    if len(subdocs) < 2:
        return errors, warnings
    relationships = collect_semantic_relationships(root, subdocs)
    for subdoc in subdocs:
        if relationships["neighbors"].get(subdoc):
            continue
        warnings.append(
            f"{subdoc}: semantic orphan; add an evidence-backed relationship sentence "
            "or confirm it is intentionally standalone"
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
            errors.append(
                f"{doc_rel}: single-page body has {issue['body_chars']} characters; "
                f"split into indexed supporting pages above {MAX_SINGLE_PAGE_BODY_CHARS}"
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


def validate(
    root: Path,
    doc_rel: str,
    *,
    metadata_override: dict | None = None,
    allow_temp_plan: bool = False,
) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        require_git_repository(root)
    except ValueError as error:
        return 1, [str(error)], warnings
    for rel_path in (DEFAULT_DOC, DEFAULT_METADATA, TEMP_PLAN):
        symlink = symlink_parent(root, rel_path)
        if symlink:
            errors.append(f"managed path parent must not be a symlink: {symlink}")
    try:
        context_symlinks = context_tree_symlinks(root, DEFAULT_DOC_DIR)
    except ValueError as error:
        errors.append(str(error))
        context_symlinks = []
    errors.extend(
        f"context path must not be a symlink: {path}"
        for path in context_symlinks
    )
    temp_plan_path = root / TEMP_PLAN
    if not allow_temp_plan and (
        temp_plan_path.exists() or temp_plan_path.is_symlink()
    ):
        errors.append(f"temporary plan must be deleted before finish: {TEMP_PLAN}")
    docs = discover_docs(root, doc_rel)
    docs = [doc for doc in docs if doc != TEMP_PLAN]
    inventory = wiki_inventory(docs, doc_rel)
    errors.extend(inventory["errors"])
    metadata_errors, metadata_warnings = validate_metadata(
        root, docs, doc_rel, metadata_override
    )
    errors.extend(metadata_errors)
    warnings.extend(metadata_warnings)
    for doc in docs:
        doc_errors, doc_warnings = validate_doc(root, doc, require_metadata=doc == doc_rel)
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
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"repo root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        require_git_repository(root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    code, messages, warnings = validate(root, DEFAULT_DOC)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    stream = sys.stderr if code else sys.stdout
    for message in messages:
        print(message, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
