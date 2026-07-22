#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and not sys.flags.dont_write_bytecode:
    os.execv(sys.executable, [sys.executable, "-B", *sys.argv])

import argparse
import errno
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_context_index import (  # noqa: E402
    CONCEPT_FIELD_LIMITS,
    INDEX_END_MARKER,
    INDEX_FIELD_LIMITS,
    INDEX_START_MARKER,
    new_area_index_markdown,
    parse_frontmatter,
    remove_context_index,
    render_context_indexes,
    replace_context_index,
    replace_or_insert_home_context_index,
    set_frontmatter_field,
    validate_entry_fields,
    wiki_inventory,
)
from project_context_agents import (  # noqa: E402
    END_MARKER as AGENT_END_MARKER,
    START_MARKER as AGENT_START_MARKER,
)
from project_context_contract import (  # noqa: E402
    GENERATOR,
    GENERATOR_VERSION,
    SCHEMA_VERSION,
)
from project_context_markdown import (  # noqa: E402
    is_external_link_target as is_external_target,
    iter_inline_links,
    iter_relative_link_targets as iter_relative_links,
)
from project_context_graph import (  # noqa: E402
    collect_semantic_relationships,
    page_content_hashes,
)
from project_context_safety import (  # noqa: E402
    atomic_write_bytes,
    atomic_write_text,
    canonical_commit_oid,
    context_tree_symlinks,
    is_utc_millisecond_timestamp,
    normalize_utc_millisecond_timestamp,
    require_expected_path,
    require_git_repository,
    require_regular_file_or_missing,
    resolve_commit_oid,
    run_git_bytes,
    symlink_parent,
)
from project_context_structure import (  # noqa: E402
    assess_primary_structure as document_structure_issues,
)


DEFAULT_DOC = "docs/project-context.md"
DEFAULT_DOC_DIR = "docs/project-context"
DEFAULT_METADATA = "docs/project-context/.metadata.json"
DEFAULT_TEMP_PLAN = "docs/project-context/_plan.md"
SNAPSHOT_EXCLUDED_PATHS = {DEFAULT_METADATA, DEFAULT_TEMP_PLAN}
PLAN_SENTINEL = "# 프로젝트 컨텍스트 임시 계획"
LEGACY_PLAN_SENTINELS = ("# Project Context Draft Plan",)
UNMAPPED_START_MARKER = "<!-- project-context:unmapped:start -->"
UNMAPPED_END_MARKER = "<!-- project-context:unmapped:end -->"
HIGH_SIGNAL_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "package.json",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "build.gradle",
    "settings.gradle",
    "pom.xml",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "pyproject.toml",
    "requirements.txt",
    "Makefile",
    "justfile",
    "Dockerfile",
    "playbook.md",
    "SKILL.md",
}
HIGH_SIGNAL_PREFIXES = (
    ".github/",
    ".gitlab/",
    ".circleci/",
    "docs/",
    "config/",
    "scripts/",
    "bin/",
    "ops/",
    "test/",
    "tests/",
    "e2e/",
    "evals/",
    "schema/",
    "schemas/",
    "db/",
    "database/",
    "migrations/",
)


def safe_json_dumps(value, *, indent: int = 2) -> str:
    rendered = json.dumps(value, indent=indent, ensure_ascii=False)
    try:
        rendered.encode("utf-8")
    except UnicodeEncodeError:
        return json.dumps(value, indent=indent, ensure_ascii=True)
    return rendered


def run_git(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        return str(error)
    return "\n".join(
        part.decode("utf-8", errors="backslashreplace").strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )


def git_output(root: Path, args: list[str]) -> str | None:
    output = run_git(root, args).strip()
    return output or None


def git_show(root: Path, ref: str, path: str) -> str:
    output = run_git(root, ["show", f"{ref}:{path}"])
    if output.startswith("fatal:"):
        return ""
    return output


def git_head(root: Path) -> tuple[str | None, str | None]:
    full = git_output(root, ["rev-parse", "HEAD"])
    short = git_output(root, ["rev-parse", "--short", "HEAD"])
    return full, short


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


def discover_docs(root: Path, primary_doc: str) -> list[str]:
    require_expected_path("primary context document", primary_doc, DEFAULT_DOC)
    primary_path = root / primary_doc
    if primary_path.is_symlink():
        raise ValueError(f"primary context document must not be a symlink: {primary_doc}")
    if primary_path.exists() and not primary_path.is_file():
        raise ValueError(f"primary context document must be a regular file: {primary_doc}")
    docs = [primary_doc]
    doc_dir = root / DEFAULT_DOC_DIR
    symlinks = context_tree_symlinks(root, DEFAULT_DOC_DIR)
    if symlinks:
        raise ValueError(
            "context document tree must not contain symlinks: " + ", ".join(symlinks)
        )
    if doc_dir.exists() and doc_dir.is_dir():
        for path in sorted(doc_dir.rglob("*.md")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in docs:
                docs.append(rel)
    return docs


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json(path: Path) -> dict | None:
    if path.is_symlink():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def is_structured_update_metadata(metadata: dict) -> bool:
    updated_at = metadata.get("updated_at")
    return (
        isinstance(updated_at, str)
        and is_utc_millisecond_timestamp(updated_at)
        and metadata.get("run_mode") in {"init", "update"}
    )


def summarize_update_metadata(metadata: dict | None) -> dict | None:
    if not metadata or not is_structured_update_metadata(metadata):
        return None
    result = {
        "updated_at": metadata["updated_at"].strip(),
        "run_mode": metadata["run_mode"],
    }
    source_commit = metadata.get("source_commit")
    if isinstance(source_commit, str) and source_commit.strip():
        result["source_commit"] = source_commit.strip()
    reviewed_commit = metadata.get("reviewed_commit")
    if isinstance(reviewed_commit, str) and reviewed_commit.strip():
        result["reviewed_commit"] = reviewed_commit.strip()
    return result


def load_last_update_metadata(root: Path, metadata_rel: str) -> tuple[dict | None, str | None]:
    if symlink_parent(root, metadata_rel):
        return None, None
    metadata = summarize_update_metadata(read_json(root / metadata_rel))
    if metadata:
        return metadata, metadata_rel
    return None, None


def read_source_commit_from_doc(root: Path, doc_rel: str) -> str | None:
    doc_path = root / doc_rel
    if doc_path.is_symlink() or not doc_path.is_file():
        return None
    source_commit = parse_frontmatter(read_text(doc_path)).get("source_commit")
    return source_commit.strip() if source_commit else None


def load_previous_context(root: Path, doc_rel: str, metadata_rel: str) -> tuple[str | None, str | None, str]:
    metadata_updated_at = None
    if not symlink_parent(root, metadata_rel):
        metadata = read_json(root / metadata_rel)
        if metadata and is_structured_update_metadata(metadata):
            source_commit = metadata.get("source_commit")
            valid_source_commit = (
                canonical_commit_oid(root, source_commit)
                if isinstance(source_commit, str)
                else None
            )
            reviewed_commit = metadata.get("reviewed_commit")
            valid_reviewed_commit = (
                canonical_commit_oid(root, reviewed_commit)
                if isinstance(reviewed_commit, str)
                else None
            )
            if (
                valid_source_commit
                and valid_reviewed_commit
                and git_commit_is_ancestor(root, valid_source_commit, valid_reviewed_commit)
                and git_commit_is_ancestor(root, valid_reviewed_commit, "HEAD")
            ):
                return valid_reviewed_commit, None, f"{metadata_rel}#reviewed_commit"
            if valid_source_commit:
                return valid_source_commit, None, f"{metadata_rel}#source_commit"
            metadata_updated_at = metadata["updated_at"].strip()
    source_commit = read_source_commit_from_doc(root, doc_rel)
    valid_document_source_commit = (
        canonical_commit_oid(root, source_commit) if source_commit else None
    )
    if valid_document_source_commit:
        return valid_document_source_commit, None, doc_rel
    if metadata_updated_at:
        return None, metadata_updated_at, metadata_rel
    return None, None, "none"


def parse_name_status_z(output: bytes) -> list[dict]:
    fields = output.split(b"\0")
    rows: list[dict] = []
    index = 0
    while index < len(fields):
        status_raw = fields[index].lstrip(b"\n")
        index += 1
        if not status_raw:
            continue
        status = status_raw.decode("ascii", errors="replace")
        if index >= len(fields):
            break
        old_or_path = fields[index].decode("utf-8", errors="backslashreplace")
        index += 1
        if status.startswith(("R", "C")):
            if index >= len(fields):
                break
            path = fields[index].decode("utf-8", errors="backslashreplace")
            index += 1
            rows.append({"status": status, "path": path, "old_path": old_or_path})
        else:
            rows.append({"status": status, "path": old_or_path})
    return rows


def parse_status_z(output: bytes) -> list[dict]:
    fields = output.split(b"\0")
    rows: list[dict] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4 or entry[2:3] != b" ":
            continue
        status = entry[:2].decode("ascii", errors="replace")
        path = entry[3:].decode("utf-8", errors="backslashreplace")
        if "R" in status or "C" in status:
            if index >= len(fields):
                break
            old_path = fields[index].decode("utf-8", errors="backslashreplace")
            index += 1
            rows.append({"status": status.strip() or status, "path": path, "old_path": old_path})
        else:
            rows.append({"status": status.strip() or status, "path": path})
    return rows


def collect_git_changes(
    root: Path,
    previous_commit: str | None,
    previous_updated_at: str | None,
) -> tuple[str, str, str, list[dict], str, list[dict]]:
    if previous_commit:
        commit_label = f"git log {previous_commit}..HEAD --name-status --oneline"
        commit_output = run_git(root, ["log", f"{previous_commit}..HEAD", "--name-status", "--oneline"])
        since_changes = parse_name_status_z(
            run_git_bytes(root, ["diff", "--name-status", "-z", f"{previous_commit}..HEAD"])
        )
        since_label = f"git diff --name-status {previous_commit}..HEAD"
    elif previous_updated_at:
        commit_label = f"git log --since {previous_updated_at} --name-status --oneline"
        commit_output = run_git(root, ["log", "--since", previous_updated_at, "--name-status", "--oneline"])
        since_changes = parse_name_status_z(
            run_git_bytes(
                root,
                ["log", "--since", previous_updated_at, "--format=", "--name-status", "-z"],
            )
        )
        since_label = commit_label
    else:
        commit_label = "git log --max-count=20 --name-status --oneline"
        commit_output = run_git(root, ["log", "--max-count=20", "--name-status", "--oneline"])
        since_changes = parse_name_status_z(
            run_git_bytes(root, ["log", "--max-count=20", "--format=", "--name-status", "-z"])
        )
        since_label = commit_label
    dirty_changes = parse_name_status_z(
        run_git_bytes(root, ["diff", "--name-status", "-z", "HEAD"])
    )
    return (
        commit_label,
        commit_output,
        since_label,
        since_changes,
        "git diff --name-status HEAD",
        dirty_changes,
    )


def collect_doc_sources(root: Path, docs: list[str]) -> dict[str, list[str]]:
    source_map: dict[str, list[str]] = {}
    for doc in docs:
        doc_path = root / doc
        if doc_path.is_symlink() or not doc_path.is_file():
            source_map[doc] = []
            continue
        doc_dir = doc_path.parent
        sources: list[str] = []
        markdown = read_text(doc_path)
        for link in iter_relative_links(markdown):
            target_path = (doc_dir / link).resolve()
            try:
                rel = target_path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel == DEFAULT_DOC or rel.startswith(f"{DEFAULT_DOC_DIR}/"):
                continue
            if rel not in sources:
                sources.append(rel)
        source_map[doc] = sources
    return source_map


def is_high_signal(path: str) -> bool:
    return path in HIGH_SIGNAL_PATHS or path.startswith(HIGH_SIGNAL_PREFIXES)


def path_affects_source(change_path: str, source_path: str) -> bool:
    return (
        change_path == source_path
        or change_path.startswith(f"{source_path}/")
        or source_path.startswith(f"{change_path}/")
    )


def is_generated_doc_path(path: str) -> bool:
    return path == DEFAULT_DOC or path.startswith(f"{DEFAULT_DOC_DIR}/")


def is_generated_metadata_path(path: str) -> bool:
    return path in {DEFAULT_METADATA, DEFAULT_TEMP_PLAN}


def strip_agent_reference(text: str) -> str:
    start = text.find(AGENT_START_MARKER)
    end = text.find(AGENT_END_MARKER)
    if start == -1 or end == -1 or start > end:
        return text.strip()
    end += len(AGENT_END_MARKER)
    return (text[:start].rstrip() + "\n" + text[end:].lstrip()).strip()


def is_agent_reference_only_change(root: Path, path: str, previous_commit: str | None) -> bool:
    if path not in {"AGENTS.md", "CLAUDE.md"}:
        return False
    old_text = git_show(root, previous_commit, path) if previous_commit else ""
    new_text = read_text(root / path)
    return strip_agent_reference(old_text) == strip_agent_reference(new_text)


def is_agent_reference_only_history(root: Path, path: str, previous_commit: str) -> bool:
    if path not in {"AGENTS.md", "CLAUDE.md"}:
        return False
    commits = run_git(
        root, ["rev-list", "--reverse", f"{previous_commit}..HEAD", "--", path]
    ).splitlines()
    if not commits:
        return False
    for commit in commits:
        parent = git_output(root, ["rev-parse", f"{commit}^"])
        old_text = git_show(root, parent, path) if parent else ""
        new_text = git_show(root, commit, path)
        if strip_agent_reference(old_text) != strip_agent_reference(new_text):
            return False
    return True


def committed_source_change_paths(root: Path, previous_commit: str) -> list[str]:
    rows = parse_name_status_z(
        run_git_bytes(
            root,
            ["log", "--format=", "--name-status", "-z", f"{previous_commit}..HEAD"],
        )
    )
    changed_paths: list[str] = []
    for row in rows:
        for key in ("old_path", "path"):
            path = row.get(key)
            if not isinstance(path, str) or path in changed_paths:
                continue
            if is_generated_doc_path(path):
                continue
            if is_agent_reference_only_history(root, path, previous_commit):
                continue
            changed_paths.append(path)
    return changed_paths


def map_affected_docs(
    docs: list[str],
    source_map: dict[str, list[str]],
    changed_paths: list[str],
    primary_doc: str,
    root: Path,
    previous_commit: str | None,
) -> tuple[dict[str, list[str]], list[str]]:
    affected: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for changed_path in changed_paths:
        if is_generated_doc_path(changed_path):
            continue
        if is_agent_reference_only_change(root, changed_path, previous_commit):
            continue
        matched_docs = []
        for doc in docs:
            for source in source_map.get(doc, []):
                if path_affects_source(changed_path, source):
                    matched_docs.append(doc)
                    break
        if is_high_signal(changed_path) and primary_doc not in matched_docs:
            matched_docs.append(primary_doc)
        if not matched_docs:
            unmapped.append(changed_path)
            continue
        for doc in matched_docs:
            affected.setdefault(doc, []).append(changed_path)
    return affected, unmapped


def dirty_source_change_paths(
    root: Path,
    change_rows: list[dict] | None = None,
) -> list[str]:
    rows = change_rows
    if rows is None:
        rows = [
            *parse_name_status_z(
                run_git_bytes(root, ["diff", "--name-status", "-z", "HEAD"])
            ),
            *parse_status_z(
                run_git_bytes(
                    root,
                    ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
                )
            ),
        ]
    paths: list[str] = []
    for row in rows:
        for key in ("old_path", "path"):
            path = row.get(key)
            if isinstance(path, str) and path not in paths:
                paths.append(path)
    return [
        path
        for path in paths
        if not is_generated_doc_path(path)
        and not is_agent_reference_only_change(root, path, "HEAD")
    ]


def require_clean_source_worktree_for_changed_docs(
    root: Path,
    docs_changed: bool,
) -> None:
    if not docs_changed:
        return
    require_clean_source_worktree(root, "record changed project context")


def require_clean_source_worktree(root: Path, action: str) -> None:
    # ponytail: metadata records commit baselines only; add a verified worktree
    # fingerprint if documenting dirty source becomes an explicit workflow.
    dirty_paths = dirty_source_change_paths(root)
    if dirty_paths:
        raise ValueError(
            f"cannot {action} with dirty source worktree changes: "
            + ", ".join(dirty_paths)
        )


def soft_diff_budget_warnings(
    source_change_paths: list[str],
    affected_docs: dict[str, list[str]],
    primary_doc: str,
) -> list[str]:
    warnings = []
    if 0 < len(source_change_paths) < 5 and len(affected_docs) > 2:
        warnings.append("fewer than 5 source files changed; update at most 1-2 docs unless current source proves broader impact")
    if len(affected_docs) > 3:
        warnings.append("more than 3 docs are affected; think deeply before broad edits and keep only source-tied changes")
    primary_changes = affected_docs.get(primary_doc, [])
    if primary_changes and all(not is_high_signal(path) for path in primary_changes):
        warnings.append("primary doc is affected only by non-high-signal changes; avoid editing the index unless top-level behavior, setup, or navigation changed")
    return warnings


def format_git_summary_section(command: str, output: str | None) -> str:
    text = output.strip() if isinstance(output, str) else ""
    return f"$ {command}\n{text if text else '(no output)'}"


def build_git_summary(plan: dict) -> str:
    sections = [
        format_git_summary_section(plan["git_status_label"], plan.get("git_status")),
        format_git_summary_section(plan["git_head_label"], plan.get("current_head") or "(unknown)"),
    ]
    if plan.get("missing_last_update_warning"):
        sections.append("No prior project-context update timestamp was found.")
    sections.append(format_git_summary_section(plan["commit_evidence_label"], plan.get("commit_evidence")))
    sections.append(format_git_summary_section(plan["dirty_changes_label"], run_git_block_from_changes(plan.get("dirty_changes", []))))
    return "\n\n".join(sections)


def run_git_block_from_changes(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = []
    for row in rows:
        status = row.get("status", "?")
        path = row.get("path", "")
        old_path = row.get("old_path")
        if old_path:
            lines.append(f"{status}\t{old_path}\t{path}")
        else:
            lines.append(f"{status}\t{path}")
    return "\n".join(lines)


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


def context_index_needs_sync(root: Path, doc_rel: str, docs: list[str]) -> bool:
    try:
        _, pending_writes = _prepare_context_index_sync(root, doc_rel, docs)
    except (OSError, ValueError):
        return True
    return bool(pending_writes)


def build_plan(root: Path, doc_rel: str, metadata_rel: str) -> dict:
    require_git_repository(root)
    full_head, short_head = git_head(root)
    git_status = run_git(root, ["status", "--short", "--untracked-files=all"])
    status_changes = parse_status_z(
        run_git_bytes(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    )
    last_update_metadata, last_update_metadata_source = load_last_update_metadata(root, metadata_rel)
    previous_commit, previous_updated_at, previous_source = load_previous_context(root, doc_rel, metadata_rel)
    docs = discover_docs(root, doc_rel)
    inventory = wiki_inventory(docs, doc_rel)
    pages = list(inventory["pages"])
    indexes = list(inventory["indexes"])
    source_map = collect_doc_sources(root, pages)
    doc_hashes = page_content_hashes(root, pages)
    current_content_hash = docs_content_hash(root, docs)
    persisted_metadata = read_json(root / metadata_rel)
    previous_doc_hashes = (
        persisted_metadata.get("doc_hashes")
        if isinstance(persisted_metadata, dict)
        and isinstance(persisted_metadata.get("doc_hashes"), dict)
        else None
    )
    changed_context_pages = (
        sorted(
            page
            for page, content_hash in doc_hashes.items()
            if previous_doc_hashes.get(page) != content_hash
        )
        if previous_doc_hashes is not None
        else []
    )
    migration_required = bool(inventory["flat_pages"]) or bool(
        persisted_metadata
        and persisted_metadata.get("schema_version") != SCHEMA_VERSION
    )
    metadata_document_state_stale = not persisted_metadata or any(
        persisted_metadata.get(field) != expected
        for field, expected in {
            "schema_version": SCHEMA_VERSION,
            "primary_doc": doc_rel,
            "pages": pages,
            "indexes": indexes,
            "doc_sources": source_map,
            "doc_hashes": doc_hashes,
            "content_hash": current_content_hash,
        }.items()
    )
    context_index_stale = context_index_needs_sync(root, doc_rel, docs)
    structure_issues = document_structure_issues(root, doc_rel, docs)
    has_previous_context = previous_commit is not None or previous_updated_at is not None
    missing_last_update_warning = None
    if (root / doc_rel).exists() and not has_previous_context:
        missing_last_update_warning = "No previous project-context update baseline was found; review recent git history before editing."
    commit_label, commit_output, since_label, since_changes, dirty_label, dirty_changes = collect_git_changes(
        root,
        previous_commit,
        previous_updated_at,
    )
    changed_paths = []
    since_rows_for_impact = since_changes if has_previous_context else []
    impact_rows = [*since_rows_for_impact, *dirty_changes, *status_changes]
    for row in impact_rows:
        old_path = row.get("old_path")
        if isinstance(old_path, str) and old_path not in changed_paths:
            changed_paths.append(old_path)
        path = row.get("path")
        if isinstance(path, str) and path not in changed_paths:
            changed_paths.append(path)
    renamed_paths = []
    for row in impact_rows:
        old_path = row.get("old_path")
        path = row.get("path")
        if isinstance(old_path, str) and isinstance(path, str):
            rename = {"old_path": old_path, "path": path}
            if rename not in renamed_paths:
                renamed_paths.append(rename)
    generated_doc_changes = [path for path in changed_paths if is_generated_doc_path(path)]
    current_change_paths = []
    for row in [*dirty_changes, *status_changes]:
        for key in ("old_path", "path"):
            path = row.get(key)
            if isinstance(path, str) and path not in current_change_paths:
                current_change_paths.append(path)
    generated_context_doc_changes = [
        path
        for path in current_change_paths
        if is_generated_doc_path(path) and not is_generated_metadata_path(path)
    ]
    if metadata_document_state_stale:
        for path in generated_doc_changes:
            if (
                not is_generated_metadata_path(path)
                and path not in generated_context_doc_changes
            ):
                generated_context_doc_changes.append(path)
        if not generated_context_doc_changes:
            generated_context_doc_changes.append(metadata_rel)
    if context_index_stale and doc_rel not in generated_context_doc_changes:
        generated_context_doc_changes.append(doc_rel)
    source_change_paths = [
        path
        for path in changed_paths
        if not is_generated_doc_path(path)
        and not is_agent_reference_only_change(root, path, previous_commit)
    ]
    current_dirty_source_change_paths = dirty_source_change_paths(
        root, [*dirty_changes, *status_changes]
    )
    affected_docs, unmapped_changes = map_affected_docs(
        pages,
        source_map,
        source_change_paths,
        doc_rel,
        root,
        previous_commit,
    )
    concepts = list(inventory["concepts"])
    semantic_relationships = collect_semantic_relationships(root, concepts)
    review_seed_pages = sorted(
        (set(affected_docs) | set(changed_context_pages)) & set(concepts)
    )
    related_review_candidates = {
        page: [
            neighbor
            for neighbor in semantic_relationships["neighbors"].get(page, [])
            if neighbor not in review_seed_pages
        ]
        for page in review_seed_pages
    }
    related_review_candidates = {
        page: neighbors
        for page, neighbors in related_review_candidates.items()
        if neighbors
    }
    budget_warnings = soft_diff_budget_warnings(source_change_paths, affected_docs, doc_rel)
    if not (root / doc_rel).exists():
        recommended_action = "create-docs"
    elif migration_required:
        recommended_action = "migrate-wiki-schema"
    elif affected_docs:
        recommended_action = "update-affected-docs"
    elif source_change_paths:
        recommended_action = "review-unmapped-changes"
    elif generated_context_doc_changes:
        recommended_action = "review-generated-doc-changes"
    elif structure_issues:
        recommended_action = "review-document-structure"
    elif not has_previous_context and since_changes:
        recommended_action = "review-recent-history"
    else:
        recommended_action = "no-op"
    required_actions = [recommended_action]
    if (
        (root / doc_rel).exists()
        and not has_previous_context
        and since_changes
        and "review-recent-history" not in required_actions
    ):
        required_actions.append("review-recent-history")
    if structure_issues and recommended_action != "review-document-structure":
        required_actions.append("review-document-structure")
    plan = {
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "current_head": full_head,
        "current_head_short": short_head,
        "git_status_label": "git status --short --untracked-files=all",
        "git_status": git_status,
        "status_changes": status_changes,
        "git_head_label": "git rev-parse HEAD",
        "previous_commit": previous_commit,
        "previous_updated_at": previous_updated_at,
        "last_update_metadata": last_update_metadata,
        "last_update_metadata_source": last_update_metadata_source,
        "has_previous_context": has_previous_context,
        "missing_last_update_warning": missing_last_update_warning,
        "previous_commit_source": previous_source,
        "metadata_path": metadata_rel,
        "primary_doc": doc_rel,
        "docs": docs,
        "pages": pages,
        "indexes": indexes,
        "wiki_structure_errors": inventory["errors"],
        "migration_required": migration_required,
        "doc_sources": source_map,
        "doc_hashes": doc_hashes,
        "changed_context_pages": changed_context_pages,
        "semantic_relationships": semantic_relationships,
        "related_review_candidates": related_review_candidates,
        "commit_evidence_label": commit_label,
        "commit_evidence": commit_output,
        "since_changes_label": since_label,
        "since_changes": since_changes,
        "dirty_changes_label": dirty_label,
        "dirty_changes": dirty_changes,
        "renamed_paths": renamed_paths,
        "source_change_paths": source_change_paths,
        "dirty_source_change_paths": current_dirty_source_change_paths,
        "generated_doc_changes": generated_doc_changes,
        "generated_context_doc_changes": generated_context_doc_changes,
        "metadata_document_state_stale": metadata_document_state_stale,
        "context_index_stale": context_index_stale,
        "structure_review_required": bool(structure_issues),
        "structure_issues": structure_issues,
        "affected_docs": affected_docs,
        "unmapped_changes": unmapped_changes,
        "soft_diff_budget_warning": "; ".join(budget_warnings) if budget_warnings else None,
        "soft_diff_budget_warnings": budget_warnings,
        "recommended_action": recommended_action,
        "required_actions": required_actions,
    }
    plan["git_summary"] = build_git_summary(plan)
    return plan


def format_changes(rows: list[dict]) -> list[str]:
    if not rows:
        return ["  (none)"]
    lines = []
    for row in rows:
        status = row.get("status", "?")
        path = row.get("path", "")
        old_path = row.get("old_path")
        if old_path:
            lines.append(f"  {status} {old_path} -> {path}")
        else:
            lines.append(f"  {status} {path}")
    return lines


def format_block(output: str | None) -> list[str]:
    if not output:
        return ["  (none)"]
    return [f"  {line}" if line else "" for line in output.splitlines()]


def format_json_block(value: dict | None) -> list[str]:
    if value is None:
        return ["  (none)"]
    return [f"  {line}" for line in safe_json_dumps(value).splitlines()]


def format_structure_issues(issues: list[dict]) -> list[str]:
    if not issues:
        return ["- (none)"]
    return [
        f"- [{issue.get('code', 'unknown')}] {issue.get('path', '(unknown)')}: "
        f"{issue.get('message', '(no message)')}"
        for issue in issues
    ]


def render_unmapped_resolution_block(paths: list[str]) -> list[str]:
    entries = [
        {"path": path, "resolution": "pending", "reason": ""}
        for path in paths
    ]
    return [
        UNMAPPED_START_MARKER,
        "```json",
        *safe_json_dumps(entries).splitlines(),
        "```",
        UNMAPPED_END_MARKER,
    ]


def parse_unmapped_resolutions(markdown: str) -> list[dict[str, str]]:
    if (
        markdown.count(UNMAPPED_START_MARKER) != 1
        or markdown.count(UNMAPPED_END_MARKER) != 1
    ):
        raise ValueError("temporary plan must have one unmapped resolution block")
    start = markdown.find(UNMAPPED_START_MARKER) + len(UNMAPPED_START_MARKER)
    end = markdown.find(UNMAPPED_END_MARKER)
    if start > end:
        raise ValueError("temporary plan unmapped resolution markers are out of order")
    block = markdown[start:end].strip()
    if not block.startswith("```json\n") or not block.endswith("\n```"):
        raise ValueError("temporary plan unmapped resolution block must be fenced JSON")
    try:
        value = json.loads(block[len("```json\n") : -len("\n```")])
    except json.JSONDecodeError as error:
        raise ValueError(
            f"temporary plan unmapped resolutions are invalid JSON: {error.msg}"
        ) from error
    if not isinstance(value, list):
        raise ValueError("temporary plan unmapped resolutions must be a list")

    resolutions: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("each unmapped resolution must be an object")
        path = entry.get("path")
        resolution = entry.get("resolution")
        reason = entry.get("reason")
        if not all(isinstance(item, str) for item in (path, resolution, reason)):
            raise ValueError("unmapped resolution path, resolution, and reason must be strings")
        if not path or path in seen_paths:
            raise ValueError("unmapped resolution paths must be non-empty and unique")
        if resolution not in {"pending", "documented", "backlog", "ignored"}:
            raise ValueError(f"invalid unmapped resolution for {path}: {resolution}")
        seen_paths.add(path)
        resolutions.append(
            {"path": path, "resolution": resolution, "reason": reason.strip()}
        )
    return resolutions


def _backlog_source_paths(root: Path) -> list[str]:
    primary_path = root / DEFAULT_DOC
    if primary_path.is_symlink() or not primary_path.is_file():
        return []
    markdown = read_text(primary_path)
    heading = re.search(r"(?m)^##\s+문서화\s+백로그\s*$", markdown)
    if not heading:
        return []
    next_heading = re.search(r"(?m)^##\s+", markdown[heading.end() :])
    end = heading.end() + next_heading.start() if next_heading else len(markdown)
    section = markdown[heading.end() : end]
    sources: list[str] = []
    for link in iter_relative_links(section):
        target = (primary_path.parent / link).resolve()
        try:
            rel = target.relative_to(root).as_posix()
        except ValueError:
            continue
        if not is_generated_doc_path(rel) and rel not in sources:
            sources.append(rel)
    return sources


def resolve_unmapped_changes(
    root: Path,
    current_plan: dict,
    plan_markdown: str | None,
) -> list[dict[str, str]]:
    entries = (
        parse_unmapped_resolutions(plan_markdown)
        if plan_markdown is not None
        else []
    )
    by_path = {entry["path"]: entry for entry in entries}
    source_changes = set(current_plan.get("source_change_paths", []))
    unmapped = set(current_plan.get("unmapped_changes", []))
    missing = sorted(unmapped - set(by_path))
    if missing:
        raise ValueError(
            "unmapped source changes require a plan resolution: " + ", ".join(missing)
        )

    backlog_sources = _backlog_source_paths(root)
    resolved: list[dict[str, str]] = []
    for path in sorted(source_changes & set(by_path)):
        entry = dict(by_path[path])
        resolution = entry["resolution"]
        reason = entry["reason"]
        if path not in unmapped:
            if resolution == "backlog":
                if not reason:
                    raise ValueError(f"backlog resolution requires a reason: {path}")
                if not any(
                    path_affects_source(path, source) for source in backlog_sources
                ):
                    raise ValueError(
                        f"backlog resolution must be linked from ## 문서화 백로그: {path}"
                    )
            else:
                entry["resolution"] = "documented"
                entry["reason"] = reason
            resolved.append(entry)
            continue

        if resolution != "ignored" or not reason:
            raise ValueError(
                f"unmapped source change must be documented, linked in backlog, "
                f"or ignored with a reason: {path}"
            )
        resolved.append(entry)
    return resolved


def format_related_review_candidates(
    related_candidates: dict[str, list[str]],
) -> list[str]:
    if not related_candidates:
        return ["- (none)"]
    lines: list[str] = []
    for doc, related_docs in related_candidates.items():
        lines.append(f"- {doc}")
        lines.extend(f"  - 검토: {related_doc}" for related_doc in related_docs)
    return lines


def format_plan(plan: dict) -> str:
    required_actions = plan.get("required_actions") or [plan.get("recommended_action")]
    lines = [
        "# 프로젝트 컨텍스트 갱신 계획",
        "",
        f"- current_head: {plan.get('current_head_short') or plan.get('current_head') or '(unknown)'}",
        f"- previous_commit: {plan.get('previous_commit') or '(none)'}",
        f"- previous_updated_at: {plan.get('previous_updated_at') or '(none)'}",
        f"- previous_commit_source: {plan.get('previous_commit_source')}",
        f"- metadata_path: {plan.get('metadata_path')}",
        f"- last_update_metadata_source: {plan.get('last_update_metadata_source') or '(none)'}",
        f"- recommended_action: {plan.get('recommended_action')}",
        f"- required_actions: {', '.join(action for action in required_actions if action)}",
        f"- migration_required: {str(bool(plan.get('migration_required'))).lower()}",
        f"- missing_last_update_warning: {plan.get('missing_last_update_warning') or '(none)'}",
        f"- soft_diff_budget_warning: {plan.get('soft_diff_budget_warning') or '(none)'}",
        "",
        "## 소프트 diff 예산 경고",
    ]
    budget_warnings = plan.get("soft_diff_budget_warnings", [])
    if budget_warnings:
        lines.extend(f"- {warning}" for warning in budget_warnings)
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "## 문서 구조 문제",
        *format_structure_issues(plan.get("structure_issues", [])),
    ])
    wiki_errors = plan.get("wiki_structure_errors", [])
    lines.extend(["", "## 위키 구조 오류"])
    if wiki_errors:
        lines.extend(f"- {error}" for error in wiki_errors)
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "## 프로젝트 컨텍스트 Git 요약",
        "",
        *format_block(plan.get("git_summary")),
        "",
        "## 마지막 갱신 메타데이터",
        *format_json_block(plan.get("last_update_metadata")),
        "",
        f"## {plan.get('git_status_label')}",
        *format_block(plan.get("git_status")),
        "",
        f"## {plan.get('git_head_label')}",
        *format_block(plan.get("current_head")),
        "",
        f"## {plan.get('commit_evidence_label')}",
        *format_block(plan.get("commit_evidence")),
        "",
        f"## {plan.get('since_changes_label')}",
        *format_changes(plan.get("since_changes", [])),
        "",
        f"## {plan.get('dirty_changes_label')}",
        *format_changes(plan.get("dirty_changes", [])),
        "",
        "## 문서 목록",
    ])
    doc_sources = plan.get("doc_sources", {})
    for doc in plan.get("docs", []):
        sources = doc_sources.get(doc, [])
        lines.append(f"- {doc}")
        if sources:
            for source in sources:
                lines.append(f"  - 소스: {source}")
        else:
            lines.append("  - 소스: (없음)")
    lines.extend(["", "## 영향 문서"])
    affected_docs = plan.get("affected_docs", {})
    if affected_docs:
        for doc, paths in affected_docs.items():
            lines.append(f"- {doc}")
            for path in paths:
                lines.append(f"  - 변경: {path}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## 관련 1-hop 검토 후보"])
    lines.extend(
        format_related_review_candidates(
            plan.get("related_review_candidates", {})
        )
    )
    lines.extend(["", "## 매핑되지 않은 변경"])
    unmapped = plan.get("unmapped_changes", [])
    if unmapped:
        lines.extend(f"- {path}" for path in unmapped)
    else:
        lines.append("- (none)")

    lines.extend(["", "## 생성 문서 변경"])
    generated_doc_changes = plan.get("generated_doc_changes", [])
    if generated_doc_changes:
        lines.extend(f"- {path}" for path in generated_doc_changes)
    else:
        lines.append("- (none)")
    lines.extend(["", "## 생성 컨텍스트 문서 변경"])
    generated_context_doc_changes = plan.get("generated_context_doc_changes", [])
    if generated_context_doc_changes:
        lines.extend(f"- {path}" for path in generated_context_doc_changes)
    else:
        lines.append("- (none)")
    lines.extend(["", "## 이름 변경 경로"])
    renamed_paths = plan.get("renamed_paths", [])
    if renamed_paths:
        for renamed_path in renamed_paths:
            lines.append(f"- {renamed_path.get('old_path')} -> {renamed_path.get('path')}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)


def format_temp_plan(plan: dict) -> str:
    required_actions = plan.get("required_actions") or [plan.get("recommended_action")]
    lines = [
        PLAN_SENTINEL,
        "",
        "project-context 실행을 마치기 전에 이 파일을 삭제한다.",
        "",
        "## 실행 요약",
        "",
        f"- current_head: {plan.get('current_head_short') or plan.get('current_head') or '(unknown)'}",
        f"- previous_commit: {plan.get('previous_commit') or '(none)'}",
        f"- previous_updated_at: {plan.get('previous_updated_at') or '(none)'}",
        f"- recommended_action: {plan.get('recommended_action')}",
        f"- required_actions: {', '.join(action for action in required_actions if action)}",
        f"- migration_required: {str(bool(plan.get('migration_required'))).lower()}",
        f"- missing_last_update_warning: {plan.get('missing_last_update_warning') or '(none)'}",
        f"- soft_diff_budget_warning: {plan.get('soft_diff_budget_warning') or '(none)'}",
        f"- last_update_metadata_source: {plan.get('last_update_metadata_source') or '(none)'}",
        "",
        "## 프로젝트 컨텍스트 Git 요약",
        "",
        *format_block(plan.get("git_summary")),
        "",
        "## 마지막 갱신 메타데이터",
        "",
        *format_json_block(plan.get("last_update_metadata")),
        "",
        "## 소프트 diff 예산 경고",
        "",
    ]
    budget_warnings = plan.get("soft_diff_budget_warnings", [])
    if budget_warnings:
        lines.extend(f"- {warning}" for warning in budget_warnings)
    else:
        lines.append("- (none)")

    lines.extend([
        "",
        "## 문서 구조 문제",
        "",
        *format_structure_issues(plan.get("structure_issues", [])),
    ])
    wiki_errors = plan.get("wiki_structure_errors", [])
    lines.extend(["", "## 위키 구조 오류", ""])
    if wiki_errors:
        lines.extend(f"- {error}" for error in wiki_errors)
    else:
        lines.append("- (none)")

    lines.extend([
        "",
        "## 예정 문서",
        "",
    ])
    for doc in plan.get("docs", []):
        lines.append(f"- {doc}")
    if not plan.get("docs"):
        lines.append("- docs/project-context.md")

    lines.extend(["", "## 문서 영향 계획", ""])
    affected_docs = plan.get("affected_docs", {})
    if affected_docs:
        for doc, paths in affected_docs.items():
            lines.append(f"- 문서: {doc}")
            for path in paths:
                lines.append(f"  - 소스 변경: {path}")
                lines.append("    - 필요한 수정: 바뀐 동작을 확인하고 오래된 주장만 갱신")
                lines.append("    - 사유: 이전 성공 실행 이후 연결된 소스가 변경됨")
    else:
        lines.append("- (none)")

    lines.extend(["", "## 관련 1-hop 검토 후보", ""])
    lines.extend(
        format_related_review_candidates(
            plan.get("related_review_candidates", {})
        )
    )

    lines.extend(["", "## 매핑되지 않은 변경", ""])
    unmapped = plan.get("unmapped_changes", [])
    if unmapped:
        for path in unmapped:
            lines.append(f"- 소스 변경: {path}")
            lines.append("  - 영향 문서: 새 섹션이나 소스 링크가 필요한지 확인")
            lines.append("  - 사유: 이 소스를 연결한 기존 컨텍스트 문서가 없음")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## 매핑되지 않은 변경 처리",
            "",
            "각 항목을 documented, backlog, ignored 중 하나로 바꾸고 backlog/ignored에는 reason을 쓴다.",
            "",
            *render_unmapped_resolution_block(unmapped),
        ]
    )

    lines.extend(["", "## 생성 컨텍스트 문서 변경", ""])
    generated_context_doc_changes = plan.get("generated_context_doc_changes", [])
    if generated_context_doc_changes:
        for path in generated_context_doc_changes:
            lines.append(f"- 컨텍스트 문서 변경: {path}")
            lines.append("  - 조치: 로컬 문서 수정이 의도됐는지, 오래됐는지, 기록할지 확인")
    else:
        lines.append("- (none)")

    lines.extend(["", "## 이름 변경 경로", ""])
    renamed_paths = plan.get("renamed_paths", [])
    if renamed_paths:
        for renamed_path in renamed_paths:
            lines.append(f"- {renamed_path.get('old_path')} -> {renamed_path.get('path')}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## 근거 기반 관계", ""])
    lines.append("- (아직 없음; 관련 개념은 소스 개념 -> 관계 의미 -> 대상 개념 형식 사용)")

    lines.extend(["", "## 보류한 범위", ""])
    lines.append("- (아직 없음; 문서 생성을 보류하면 영역, 소스 근거, 사유를 기록)")

    lines.extend(["", "## 소스 근거", ""])
    doc_sources = plan.get("doc_sources", {})
    if doc_sources:
        for doc, sources in doc_sources.items():
            lines.append(f"- {doc}")
            if sources:
                for source in sources:
                    lines.append(f"  - {source}")
            else:
                lines.append("  - (아직 없음)")
    else:
        lines.append("- (아직 없음)")

    lines.extend(["", "## 남은 질문", "", "- (아직 없음)"])
    return "\n".join(lines) + "\n"


def has_project_context_plan_sentinel(markdown: str) -> bool:
    return any(
        markdown.startswith(f"{sentinel}\n")
        for sentinel in (PLAN_SENTINEL, *LEGACY_PLAN_SENTINELS)
    )


def write_temp_plan(root: Path, plan_rel: str, plan: dict) -> Path:
    require_git_repository(root)
    require_expected_path("temporary plan path", plan_rel, DEFAULT_TEMP_PLAN)
    require_clean_source_worktree(root, "write project context plan")
    symlink = symlink_parent(root, plan_rel)
    if symlink:
        raise ValueError(f"temporary plan parent must not be a symlink: {symlink}")
    plan_path = root / plan_rel
    if plan_path.is_symlink():
        raise ValueError(f"temporary plan path must not be a symlink: {plan_rel}")
    if plan_path.exists():
        if not plan_path.is_file():
            raise ValueError(f"temporary plan path must be a regular file: {plan_rel}")
        if not has_project_context_plan_sentinel(read_text(plan_path)):
            raise ValueError("refusing to overwrite a non-project-context plan")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(plan_path, format_temp_plan(plan))
    return plan_path


def delete_temp_plan(root: Path, plan_rel: str) -> tuple[str, bool]:
    require_git_repository(root)
    require_expected_path("temporary plan path", plan_rel, DEFAULT_TEMP_PLAN)
    symlink = symlink_parent(root, plan_rel)
    if symlink:
        raise ValueError(f"temporary plan parent must not be a symlink: {symlink}")
    plan_path = root / plan_rel
    if not plan_path.exists() and not plan_path.is_symlink():
        return f"temporary plan absent: {plan_rel}", False
    if plan_path.is_symlink():
        raise ValueError(f"temporary plan path must not be a symlink: {plan_rel}")
    if not plan_path.is_file():
        raise ValueError(f"temporary plan path must be a regular file: {plan_rel}")
    if not has_project_context_plan_sentinel(read_text(plan_path)):
        raise ValueError("refusing to delete a non-project-context plan")
    plan_path.unlink()
    return f"temporary plan deleted: {plan_rel}", True


def _split_link_suffix(target: str) -> tuple[str, str]:
    positions = [position for marker in ("#", "?") if (position := target.find(marker)) >= 0]
    if not positions:
        return target, ""
    split_at = min(positions)
    return target[:split_at], target[split_at:]


def _rewrite_migrated_links(
    root: Path,
    markdown: str,
    old_doc: str,
    new_doc: str,
    moves: dict[str, str],
) -> str:
    replacements: list[tuple[int, int, str]] = []
    old_dir = (root / old_doc).parent
    new_dir = (root / new_doc).parent
    for target, start, end in iter_inline_links(markdown):
        path_part, suffix = _split_link_suffix(target)
        if (
            not path_part
            or is_external_target(target)
            or path_part.startswith("/")
        ):
            continue
        old_target = (old_dir / unquote(path_part)).resolve()
        try:
            old_target_rel = old_target.relative_to(root).as_posix()
        except ValueError:
            continue
        next_target_rel = moves.get(old_target_rel, old_target_rel)
        if old_doc == new_doc and next_target_rel == old_target_rel:
            continue
        relative = Path(
            os.path.relpath(root / next_target_rel, start=new_dir)
        ).as_posix()
        replacements.append((start, end, quote(relative, safe="/:@") + suffix))

    result = markdown
    for start, end, replacement in reversed(replacements):
        result = result[:start] + replacement + result[end:]
    return result


def _ensure_index_markers(markdown: str, doc: str) -> str:
    start_count = markdown.count(INDEX_START_MARKER)
    end_count = markdown.count(INDEX_END_MARKER)
    if start_count == end_count == 1:
        return markdown
    if start_count or end_count:
        raise ValueError(f"{doc}: context index must have exactly one start and end marker")
    block = f"{INDEX_START_MARKER}\n{INDEX_END_MARKER}"
    evidence = re.search(r"(?m)^##\s+근거\s*$", markdown)
    if evidence:
        return markdown[: evidence.start()].rstrip() + f"\n\n{block}\n\n" + markdown[evidence.start() :]
    return markdown.rstrip() + f"\n\n{block}\n"


def _validate_migration_fields(
    documents: dict[str, str],
    concepts: list[str],
    indexes: list[str],
) -> list[str]:
    errors: list[str] = []
    for doc, limits in [
        *((concept, CONCEPT_FIELD_LIMITS) for concept in concepts),
        *((index, INDEX_FIELD_LIMITS) for index in indexes),
    ]:
        _, field_errors = validate_entry_fields(
            doc, parse_frontmatter(documents[doc]), limits
        )
        errors.extend(field_errors)
    return errors


def _resolve_migration_commit_oid(root: Path, value: object) -> str | None:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9a-fA-F]{7,64}", value.strip()) is None
    ):
        return None
    return resolve_commit_oid(root, value.strip())


def _migration_source_commit(
    root: Path,
    doc_rel: str,
    metadata: dict,
) -> str:
    for candidate in (
        metadata.get("source_commit"),
        read_source_commit_from_doc(root, doc_rel),
    ):
        resolved = _resolve_migration_commit_oid(root, candidate)
        if resolved:
            return resolved
    raise ValueError(
        "migration requires a resolvable full or abbreviated source_commit "
        "in metadata or primary frontmatter"
    )


def _migration_updated_at(root: Path, doc_rel: str) -> str:
    fields = parse_frontmatter(read_text(root / doc_rel))
    normalized = normalize_utc_millisecond_timestamp(fields.get("updated_at"))
    if normalized is None:
        raise ValueError(
            f"{doc_rel}: migration requires an ISO-8601 updated_at with timezone"
        )
    return normalized


def _prepare_wiki_migration(root: Path, doc_rel: str) -> tuple[dict, dict[str, str]]:
    require_git_repository(root)
    require_expected_path("primary context document", doc_rel, DEFAULT_DOC)
    docs = [doc for doc in discover_docs(root, doc_rel) if doc != DEFAULT_TEMP_PLAN]
    metadata_path = root / DEFAULT_METADATA
    metadata = read_json(metadata_path)
    if metadata_path.exists() and metadata is None:
        raise ValueError(
            f"invalid migration metadata; repair or remove {DEFAULT_METADATA}"
        )
    metadata = metadata or {}
    migration_source_commit = _migration_source_commit(root, doc_rel, metadata)
    migration_updated_at = _migration_updated_at(root, doc_rel)
    source_schema_version = metadata.get("schema_version", 1)
    if source_schema_version not in {1, SCHEMA_VERSION}:
        raise ValueError(
            f"unsupported project-context schema_version: {source_schema_version}"
        )
    inventory = wiki_inventory(docs, doc_rel, require_indexes=False)
    errors = [
        error
        for error in inventory["errors"]
        if "legacy flat page must be migrated" not in error
    ]
    moves: dict[str, str] = {}
    for flat_doc in inventory["flat_pages"]:
        stem = Path(flat_doc).stem
        destination = f"{DEFAULT_DOC_DIR}/{stem}/overview.md"
        destination_path = root / destination
        if destination in docs or destination_path.exists() or destination_path.is_symlink():
            errors.append(f"{flat_doc}: migration destination already exists: {destination}")
        moves[flat_doc] = destination

    future_concepts = sorted([*inventory["concepts"], *moves.values()])
    future_indexes = sorted(
        {
            f"{DEFAULT_DOC_DIR}/{Path(concept).parent.name}/index.md"
            for concept in future_concepts
        }
    )
    existing_indexes = set(inventory["indexes"])
    empty_indexes = sorted(existing_indexes - set(future_indexes))
    for index in empty_indexes:
        errors.append(f"{index}: empty area index is not allowed")
    if errors:
        raise ValueError("\n".join(errors))

    documents: dict[str, str] = {}
    source_docs = [doc_rel, *inventory["concepts"], *inventory["flat_pages"], *inventory["indexes"]]
    for old_doc in source_docs:
        path = root / old_doc
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"context document must be a regular file: {old_doc}")
        new_doc = moves.get(old_doc, old_doc)
        markdown = _rewrite_migrated_links(
            root, read_text(path), old_doc, new_doc, moves
        )
        if new_doc in future_concepts and not parse_frontmatter(markdown).get("type"):
            markdown = set_frontmatter_field(markdown, "type", "concept")
        if new_doc == doc_rel:
            markdown = set_frontmatter_field(
                markdown, "source_commit", migration_source_commit
            )
            markdown = set_frontmatter_field(
                markdown, "updated_at", migration_updated_at
            )
            markdown = set_frontmatter_field(
                markdown, "mode", "multi-page" if future_concepts else "single-page"
            )
            if future_concepts:
                markdown = _ensure_index_markers(markdown, new_doc)
        elif new_doc in future_indexes:
            markdown = set_frontmatter_field(
                markdown, "generated_by", "project-context-index"
            )
            markdown = _ensure_index_markers(markdown, new_doc)
        documents[new_doc] = markdown

    created_indexes = sorted(set(future_indexes) - existing_indexes)
    for index_doc in created_indexes:
        area = Path(index_doc).parent.name
        documents[index_doc] = new_area_index_markdown(area)

    field_errors = _validate_migration_fields(
        documents, future_concepts, future_indexes
    )
    if field_errors:
        raise ValueError("\n".join(field_errors))

    plan = {
        "from_schema_version": source_schema_version,
        "to_schema_version": SCHEMA_VERSION,
        "moves": moves,
        "created_indexes": created_indexes,
        "updated_docs": sorted(documents),
        "pages": [doc_rel, *future_concepts],
        "indexes": future_indexes,
    }
    return plan, documents


def build_wiki_migration(root: Path, doc_rel: str) -> dict:
    plan, _ = _prepare_wiki_migration(root, doc_rel)
    return plan


def apply_wiki_migration(root: Path, doc_rel: str, run_mode: str) -> dict:
    plan_path = root / DEFAULT_TEMP_PLAN
    if plan_path.exists() or plan_path.is_symlink():
        raise ValueError(
            f"temporary plan must be deleted before migration: {DEFAULT_TEMP_PLAN}"
        )
    require_clean_source_worktree(root, "apply project context migration")
    plan, documents = _prepare_wiki_migration(root, doc_rel)
    previous_metadata = read_json(root / DEFAULT_METADATA) or {}
    migration_source_commit = parse_frontmatter(documents[doc_rel])["source_commit"]
    metadata_reviewed_commit = previous_metadata.get("reviewed_commit")
    previous_reviewed_commit = _resolve_migration_commit_oid(
        root, metadata_reviewed_commit
    )
    migration_reviewed_commit = (
        previous_reviewed_commit
        if previous_reviewed_commit
        and migration_source_commit
        and git_commit_is_ancestor(
            root, migration_source_commit, previous_reviewed_commit
        )
        and git_commit_is_ancestor(root, previous_reviewed_commit, "HEAD")
        else migration_source_commit
    )
    migration_paths = sorted(
        set(documents) | set(plan["moves"]) | {DEFAULT_METADATA}
    )
    originals, created_parent_dirs = _snapshot_migration_state(
        root, migration_paths
    )
    written_docs: list[str] = []
    try:
        for target, markdown in documents.items():
            target_path = root / target
            if (
                target_path.is_file()
                and not target_path.is_symlink()
                and read_text(target_path) == markdown
            ):
                continue
            atomic_write_text(target_path, markdown)
            written_docs.append(target)
        for source, target in plan["moves"].items():
            if source != target:
                (root / source).unlink()

        sync_result = sync_context_index(root, doc_rel)
        docs = discover_docs(root, doc_rel)
        current_hash = docs_content_hash(root, docs)
        metadata = record_metadata(
            root,
            doc_rel,
            DEFAULT_METADATA,
            run_mode,
            True,
            current_hash,
            reviewed_commit_override=migration_reviewed_commit,
        )
    except BaseException:
        _restore_context_writes(root, originals, "migration path")
        _remove_created_context_directories(root, created_parent_dirs)
        raise
    return {
        **plan,
        "applied": True,
        "written_docs": sorted(written_docs),
        "sync": sync_result,
        "metadata": metadata,
    }


def _prepare_context_index_sync(
    root: Path,
    doc_rel: str,
    docs: list[str] | None = None,
) -> tuple[dict, dict[str, str]]:
    require_git_repository(root)
    require_expected_path("primary context document", doc_rel, DEFAULT_DOC)
    doc_path = root / doc_rel
    if doc_path.is_symlink() or not doc_path.is_file():
        raise ValueError(f"primary context document must be a regular file: {doc_rel}")
    current_docs = docs if docs is not None else discover_docs(root, doc_rel)
    current_docs = [doc for doc in current_docs if doc != DEFAULT_TEMP_PLAN]
    inventory = wiki_inventory(current_docs, doc_rel, require_indexes=False)
    if inventory["errors"]:
        raise ValueError("\n".join(inventory["errors"]))
    concepts = list(inventory["concepts"])
    documents = {
        concept: read_text(root / concept)
        for concept in concepts
    }
    field_errors = _validate_migration_fields(documents, concepts, [])
    if field_errors:
        raise ValueError("\n".join(field_errors))

    created_documents: dict[str, str] = {}
    for index_doc in inventory["expected_indexes"]:
        index_path = root / index_doc
        if index_doc in inventory["indexes"]:
            continue
        parent_symlink = symlink_parent(root, index_doc)
        if parent_symlink:
            raise ValueError(
                f"area index parent must not be a symlink: {parent_symlink}"
            )
        if index_path.exists() or index_path.is_symlink():
            raise ValueError(
                f"area index must be a regular file or absent: {index_doc}"
            )
        created_documents[index_doc] = new_area_index_markdown(
            Path(index_doc).parent.name
        )

    future_docs = sorted(set(current_docs) | set(created_documents))
    rendered_indexes, errors = render_context_indexes(
        root,
        doc_rel,
        future_docs,
        markdown_overrides=created_documents,
    )
    if errors or rendered_indexes is None:
        raise ValueError("\n".join(errors))
    if not rendered_indexes:
        current_markdown = read_text(doc_path)
        next_markdown, changed = remove_context_index(current_markdown)
        pending_writes = {doc_rel: next_markdown} if changed else {}
        return {
            "changed": changed,
            "skipped": not changed,
            "reason": "wiki has no concept pages",
            "doc": doc_rel,
            "changed_docs": [doc_rel] if changed else [],
            "created_indexes": [],
            "indexes": 0,
        }, pending_writes

    pending_writes: dict[str, str] = {}
    for index_doc, rendered_index in rendered_indexes.items():
        index_path = root / index_doc
        current_markdown = created_documents.get(index_doc)
        if current_markdown is None and (
            index_path.is_symlink() or not index_path.is_file()
        ):
            raise ValueError(f"index document must be a regular file: {index_doc}")
        current_markdown = current_markdown or read_text(index_path)
        replace_index = (
            replace_or_insert_home_context_index
            if index_doc == doc_rel
            else replace_context_index
        )
        next_markdown, changed = replace_index(current_markdown, rendered_index)
        if changed:
            pending_writes[index_doc] = next_markdown
    created_indexes = sorted(created_documents)
    return {
        "changed": bool(created_indexes or pending_writes),
        "skipped": False,
        "doc": doc_rel,
        "changed_docs": sorted(set(created_indexes) | set(pending_writes)),
        "created_indexes": created_indexes,
        "indexes": len(rendered_indexes) - 1,
    }, pending_writes


def _restore_context_writes(
    root: Path,
    originals: dict[str, bytes | None],
    label: str = "context index path",
) -> None:
    for doc in sorted(originals, reverse=True):
        path = root / doc
        original = originals[doc]
        require_regular_file_or_missing(root, doc, label)
        if original is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(path, original)


def _snapshot_migration_state(
    root: Path,
    paths: list[str],
) -> tuple[dict[str, bytes | None], list[str]]:
    originals: dict[str, bytes | None] = {}
    created_parent_dirs: set[str] = set()
    for rel_path in paths:
        if not is_generated_doc_path(rel_path):
            raise ValueError(f"migration path is outside managed docs: {rel_path}")
        require_regular_file_or_missing(root, rel_path, "migration path")
        originals[rel_path] = snapshot_file_bytes(root / rel_path)
        for parent in Path(rel_path).parents:
            parent_rel = parent.as_posix()
            if not parent_rel.startswith(f"{DEFAULT_DOC_DIR}/"):
                continue
            parent_path = root / parent
            if not parent_path.exists() and not parent_path.is_symlink():
                created_parent_dirs.add(parent_rel)
    return originals, sorted(created_parent_dirs)


def _remove_created_context_directories(root: Path, directories: list[str]) -> None:
    for directory in sorted(
        directories,
        key=lambda item: (len(Path(item).parts), item),
        reverse=True,
    ):
        path = root / directory
        if path.exists():
            path.rmdir()


def _apply_context_writes(
    root: Path,
    pending_writes: dict[str, str],
) -> dict[str, bytes | None]:
    originals: dict[str, bytes | None] = {}
    for doc in pending_writes:
        if doc != DEFAULT_DOC and not doc.startswith(f"{DEFAULT_DOC_DIR}/"):
            raise ValueError(f"context index path is outside managed docs: {doc}")
        require_regular_file_or_missing(root, doc, "context index path")
        originals[doc] = snapshot_file_bytes(root / doc)
    try:
        for doc, markdown in pending_writes.items():
            atomic_write_text(root / doc, markdown)
    except BaseException:
        _restore_context_writes(root, originals)
        raise
    return originals


def sync_context_index(root: Path, doc_rel: str) -> dict:
    result, pending_writes = _prepare_context_index_sync(root, doc_rel)
    require_clean_source_worktree_for_changed_docs(root, bool(pending_writes))
    _apply_context_writes(root, pending_writes)
    return result


def record_metadata(
    root: Path,
    doc_rel: str,
    metadata_rel: str,
    run_mode: str,
    if_changed: bool,
    before_hash: str | None,
    *,
    write: bool = True,
    unmapped_resolutions: list[dict[str, str]] | None = None,
    reviewed_commit_override: str | None = None,
) -> dict:
    require_expected_path("primary context document", doc_rel, DEFAULT_DOC)
    require_expected_path("metadata path", metadata_rel, DEFAULT_METADATA)
    require_git_repository(root)
    require_regular_file_or_missing(root, metadata_rel, "metadata path")
    full_head, short_head = git_head(root)
    docs = discover_docs(root, doc_rel)
    inventory = wiki_inventory(docs, doc_rel)
    if inventory["errors"]:
        raise ValueError("\n".join(inventory["errors"]))
    pages = list(inventory["pages"])
    indexes = list(inventory["indexes"])
    source_map = collect_doc_sources(root, pages)
    doc_hashes = page_content_hashes(root, pages)
    content_hash = docs_content_hash(root, docs)
    previous_metadata = read_json(root / metadata_rel) or {}
    resolutions = unmapped_resolutions or []
    override_reviewed_commit = (
        canonical_commit_oid(root, reviewed_commit_override)
        if reviewed_commit_override
        else None
    )
    if reviewed_commit_override and override_reviewed_commit is None:
        raise ValueError("reviewed_commit override must be a canonical full commit ID")
    docs_unchanged = if_changed and (
        (bool(before_hash) and before_hash == content_hash)
        or previous_metadata.get("content_hash") == content_hash
    )
    require_clean_source_worktree_for_changed_docs(root, not docs_unchanged)
    previous_source_commit = previous_metadata.get("source_commit")
    valid_previous_source_commit = (
        canonical_commit_oid(root, previous_source_commit)
        if isinstance(previous_source_commit, str)
        else None
    )
    document_source_ref = read_source_commit_from_doc(root, doc_rel)
    valid_document_source_commit = (
        canonical_commit_oid(root, document_source_ref)
        if document_source_ref
        else None
    )
    review_source_commit = valid_document_source_commit or valid_previous_source_commit
    if override_reviewed_commit and review_source_commit and (
        not git_commit_is_ancestor(root, review_source_commit, override_reviewed_commit)
        or not git_commit_is_ancestor(root, override_reviewed_commit, "HEAD")
    ):
        raise ValueError(
            "reviewed_commit override must be between source_commit and HEAD"
        )
    previous_reviewed_commit = previous_metadata.get("reviewed_commit")
    canonical_previous_reviewed_commit = (
        canonical_commit_oid(root, previous_reviewed_commit)
        if isinstance(previous_reviewed_commit, str)
        else None
    )
    valid_previous_reviewed_commit = (
        canonical_previous_reviewed_commit
        if canonical_previous_reviewed_commit
        and review_source_commit
        and git_commit_is_ancestor(root, review_source_commit, canonical_previous_reviewed_commit)
        and git_commit_is_ancestor(root, canonical_previous_reviewed_commit, "HEAD")
        else None
    )
    previous_source_commit_short = previous_metadata.get("source_commit_short")
    resolved_previous_source_commit_short = (
        resolve_commit_oid(root, previous_source_commit_short)
        if isinstance(previous_source_commit_short, str)
        else None
    )
    source_metadata_needs_repair = bool(valid_document_source_commit) and (
        valid_previous_source_commit != valid_document_source_commit
        or resolved_previous_source_commit_short != valid_document_source_commit
    )
    review_baseline = (
        valid_previous_reviewed_commit
        or valid_previous_source_commit
        or valid_document_source_commit
    )
    committed_source_changes = (
        committed_source_change_paths(root, review_baseline)
        if docs_unchanged
        and review_baseline
        and full_head
        and git_output(root, ["rev-parse", review_baseline]) != full_head
        else []
    )
    expected_derived_metadata = {
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "primary_doc": doc_rel,
        "pages": pages,
        "indexes": indexes,
        "doc_sources": source_map,
        "doc_hashes": doc_hashes,
        "unmapped_resolutions": resolutions,
        "content_hash": content_hash,
    }
    previous_updated_at = previous_metadata.get("updated_at")
    metadata_needs_rewrite = (
        valid_previous_reviewed_commit is None
        or (
            override_reviewed_commit is not None
            and valid_previous_reviewed_commit != override_reviewed_commit
        )
        or source_metadata_needs_repair
        or not isinstance(previous_updated_at, str)
        or not is_utc_millisecond_timestamp(previous_updated_at)
        or previous_metadata.get("run_mode") not in {"init", "update"}
        or any(
            previous_metadata.get(field) != expected
            for field, expected in expected_derived_metadata.items()
        )
    )

    if docs_unchanged and not metadata_needs_rewrite and not committed_source_changes:
        result = {
            "skipped": True,
            "reason": "documentation unchanged and no committed source review baseline to advance",
            "metadata_path": metadata_rel,
            "source_commit": previous_metadata.get("source_commit"),
            "source_commit_short": previous_metadata.get("source_commit_short"),
            "reviewed_commit": previous_metadata.get("reviewed_commit"),
            "pages": pages,
            "indexes": indexes,
            "content_hash": content_hash,
        }
        if not write:
            result["candidate"] = previous_metadata
        return result

    updated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if docs_unchanged:
        # ponytail: reviewed_commit covers committed HEAD only; add a worktree fingerprint if repeated pre-commit reviews become costly.
        source_commit = valid_document_source_commit or valid_previous_source_commit
        source_commit_short = (
            git_output(root, ["rev-parse", "--short", source_commit])
            if source_commit
            else previous_metadata.get("source_commit_short")
        )
    else:
        source_commit = full_head
        source_commit_short = short_head
    target_reviewed_commit = override_reviewed_commit or full_head
    if source_commit and target_reviewed_commit and (
        not git_commit_is_ancestor(root, source_commit, target_reviewed_commit)
        or not git_commit_is_ancestor(root, target_reviewed_commit, "HEAD")
    ):
        raise ValueError("reviewed_commit must be between source_commit and HEAD")

    metadata = {
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "updated_at": updated_at,
        "run_mode": run_mode,
        "source_commit": source_commit,
        "source_commit_short": source_commit_short,
        "reviewed_commit": target_reviewed_commit,
        "primary_doc": doc_rel,
        "pages": pages,
        "indexes": indexes,
        "doc_sources": source_map,
        "doc_hashes": doc_hashes,
        "unmapped_resolutions": resolutions,
        "content_hash": content_hash,
    }
    if not write:
        return {
            "skipped": False,
            "review_only": docs_unchanged,
            "candidate": metadata,
        }
    metadata_path = root / metadata_rel
    atomic_write_text(metadata_path, f"{safe_json_dumps(metadata)}\n")
    return {**metadata, "review_only": True} if docs_unchanged else metadata


def finalize_context(
    root: Path,
    doc_rel: str,
    metadata_rel: str,
    run_mode: str,
    if_changed: bool,
    before_hash: str | None,
) -> dict:
    from validate_project_context import validate

    require_git_repository(root)
    require_expected_path("primary context document", doc_rel, DEFAULT_DOC)
    require_expected_path("metadata path", metadata_rel, DEFAULT_METADATA)
    require_regular_file_or_missing(root, metadata_rel, "metadata path")

    current_docs = [
        doc
        for doc in discover_docs(root, doc_rel)
        if doc != DEFAULT_TEMP_PLAN
    ]
    sync_result, pending_index_writes = _prepare_context_index_sync(
        root, doc_rel, current_docs
    )
    docs_changed = (
        before_hash is None
        or docs_content_hash(root, current_docs) != before_hash
    )
    require_clean_source_worktree_for_changed_docs(
        root, docs_changed or bool(pending_index_writes)
    )

    plan_path = root / DEFAULT_TEMP_PLAN
    plan_bytes = snapshot_file_bytes(plan_path)
    if (plan_path.exists() or plan_path.is_symlink()) and plan_bytes is None:
        raise ValueError(
            f"temporary plan must be a regular file: {DEFAULT_TEMP_PLAN}"
        )
    plan_markdown = (
        plan_bytes.decode("utf-8") if plan_bytes is not None else None
    )
    metadata_path = root / metadata_rel
    original_metadata = snapshot_file_bytes(metadata_path)
    plan_deleted = False
    metadata_written = False
    original_indexes: dict[str, bytes | None] = {}
    try:
        original_indexes = _apply_context_writes(root, pending_index_writes)
        current_plan = build_plan(root, doc_rel, metadata_rel)
        resolutions = resolve_unmapped_changes(root, current_plan, plan_markdown)
        preview = record_metadata(
            root,
            doc_rel,
            metadata_rel,
            run_mode,
            if_changed,
            before_hash,
            write=False,
            unmapped_resolutions=resolutions,
        )
        candidate = preview["candidate"]
        code, messages, warnings = validate(
            root,
            doc_rel,
            metadata_override=candidate,
            allow_temp_plan=True,
        )
        if code != 0:
            raise ValueError(
                "candidate metadata validation failed:\n" + "\n".join(messages)
            )
        if plan_markdown is not None:
            delete_temp_plan(root, DEFAULT_TEMP_PLAN)
            plan_deleted = True
        if not preview["skipped"]:
            atomic_write_text(metadata_path, f"{safe_json_dumps(candidate)}\n")
            metadata_written = True
        final_code, final_messages, final_warnings = validate(root, doc_rel)
        if final_code != 0:
            raise ValueError(
                "final project-context validation failed:\n"
                + "\n".join(final_messages)
            )
    except BaseException:
        if metadata_written:
            if original_metadata is None:
                metadata_path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(metadata_path, original_metadata)
        if plan_deleted and plan_bytes is not None:
            atomic_write_bytes(plan_path, plan_bytes)
        if original_indexes:
            _restore_context_writes(root, original_indexes)
        raise

    return {
        "finalized": True,
        "metadata_written": metadata_written,
        "review_only": bool(preview.get("review_only")),
        "sync": sync_result,
        "unmapped_resolutions": resolutions,
        "messages": final_messages,
        "warnings": final_warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or record Codex-native project context updates.")
    parser.add_argument("command", choices=["plan", "write-plan", "delete-plan", "migrate", "sync-index", "snapshot", "record", "finalize"], help="plan prints update impact; write-plan creates a temporary docs plan; delete-plan removes the temporary plan safely; migrate plans or applies schema v2 hierarchy migration; sync-index refreshes deterministic wiki indexes; snapshot prints the current docs content hash; record writes metadata directly; finalize syncs indexes, validates a metadata candidate, removes the plan, and records atomically.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root.")
    parser.add_argument("--mode", choices=["init", "update"], default="update", help="Project context run mode stored in metadata.")
    parser.add_argument("--if-changed", action="store_true", help="Preserve the documentation source commit when docs are unchanged while recording newly reviewed commits.")
    parser.add_argument("--before-hash", help="Docs content hash captured before the run. With --if-changed, metadata is skipped when it still matches.")
    parser.add_argument("--apply", action="store_true", help="Apply the migration. Without this flag, migrate is read-only.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
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
    if args.command in {"plan", "write-plan"}:
        try:
            plan = build_plan(root, DEFAULT_DOC, DEFAULT_METADATA)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.command == "write-plan":
            if (root / DEFAULT_TEMP_PLAN).is_symlink():
                print(f"temporary plan path must not be a symlink: {DEFAULT_TEMP_PLAN}", file=sys.stderr)
                return 1
            try:
                plan_path = write_temp_plan(root, DEFAULT_TEMP_PLAN, plan)
            except ValueError as error:
                print(str(error), file=sys.stderr)
                return 1
            if args.json:
                print(safe_json_dumps(
                    {
                        "plan_path": DEFAULT_TEMP_PLAN,
                        "recommended_action": plan.get("recommended_action"),
                        "required_actions": plan.get("required_actions", []),
                        "previous_commit": plan.get("previous_commit"),
                        "previous_updated_at": plan.get("previous_updated_at"),
                        "previous_commit_source": plan.get("previous_commit_source"),
                        "last_update_metadata": plan.get("last_update_metadata"),
                        "last_update_metadata_source": plan.get("last_update_metadata_source"),
                        "docs": plan.get("docs", []),
                        "pages": plan.get("pages", []),
                        "indexes": plan.get("indexes", []),
                        "migration_required": plan.get("migration_required", False),
                        "wiki_structure_errors": plan.get("wiki_structure_errors", []),
                        "missing_last_update_warning": plan.get("missing_last_update_warning"),
                        "soft_diff_budget_warning": plan.get("soft_diff_budget_warning"),
                        "soft_diff_budget_warnings": plan.get("soft_diff_budget_warnings", []),
                        "structure_review_required": plan.get("structure_review_required", False),
                        "structure_issues": plan.get("structure_issues", []),
                        "git_summary": plan.get("git_summary"),
                        "source_change_paths": plan.get("source_change_paths", []),
                        "affected_docs": plan.get("affected_docs", {}),
                        "changed_context_pages": plan.get("changed_context_pages", []),
                        "related_review_candidates": plan.get("related_review_candidates", {}),
                        "unmapped_changes": plan.get("unmapped_changes", []),
                        "generated_context_doc_changes": plan.get("generated_context_doc_changes", []),
                        "renamed_paths": plan.get("renamed_paths", []),
                    }
                ))
            else:
                print(f"draft plan written: {plan_path.relative_to(root).as_posix()}")
                print(f"recommended_action: {plan.get('recommended_action')}")
            return 0
        if args.json:
            print(safe_json_dumps(plan))
        else:
            print(format_plan(plan))
        return 0

    if args.command == "delete-plan":
        try:
            message, deleted = delete_temp_plan(root, DEFAULT_TEMP_PLAN)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.json:
            print(safe_json_dumps({"plan_path": DEFAULT_TEMP_PLAN, "deleted": deleted}))
        else:
            print(message)
        return 0

    if args.command == "migrate":
        if args.apply and (
            (root / DEFAULT_TEMP_PLAN).exists()
            or (root / DEFAULT_TEMP_PLAN).is_symlink()
        ):
            print(
                f"temporary plan must be deleted before migration: {DEFAULT_TEMP_PLAN}",
                file=sys.stderr,
            )
            return 1
        try:
            result = (
                apply_wiki_migration(root, DEFAULT_DOC, args.mode)
                if args.apply
                else build_wiki_migration(root, DEFAULT_DOC)
            )
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.json:
            print(safe_json_dumps(result))
        elif args.apply:
            print(f"wiki migration applied: schema {SCHEMA_VERSION}")
            print(f"moved pages: {len(result.get('moves', {}))}")
            print(f"created indexes: {len(result.get('created_indexes', []))}")
        else:
            print(f"wiki migration plan: schema {result.get('from_schema_version')} -> {SCHEMA_VERSION}")
            print(f"moved pages: {len(result.get('moves', {}))}")
            print(f"created indexes: {len(result.get('created_indexes', []))}")
            print("read-only; pass --apply to write")
        return 0

    if args.command == "sync-index":
        try:
            result = sync_context_index(root, DEFAULT_DOC)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.json:
            print(safe_json_dumps(result))
        elif result.get("skipped"):
            print(f"context index unchanged: {result.get('reason')}")
        else:
            state = "updated" if result.get("changed") else "current"
            print(f"context indexes {state}: {DEFAULT_DOC}")
            print(f"area indexes: {result.get('indexes')}")
        return 0

    if args.command == "snapshot":
        try:
            docs = discover_docs(root, DEFAULT_DOC)
            content_hash = docs_content_hash(root, docs)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.json:
            print(safe_json_dumps({"content_hash": content_hash, "docs": docs}))
        else:
            print(content_hash)
        return 0

    if args.command == "finalize":
        try:
            result = finalize_context(
                root,
                DEFAULT_DOC,
                DEFAULT_METADATA,
                args.mode,
                args.if_changed,
                args.before_hash,
            )
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.json:
            print(safe_json_dumps(result))
        else:
            state = "written" if result["metadata_written"] else "unchanged"
            print(f"project context finalized: metadata {state}")
            print(f"warnings: {len(result['warnings'])}")
        return 0

    plan_path = root / DEFAULT_TEMP_PLAN
    if plan_path.exists() or plan_path.is_symlink():
        print(f"temporary plan must be deleted before recording metadata: {DEFAULT_TEMP_PLAN}", file=sys.stderr)
        return 1
    doc_path = root / DEFAULT_DOC
    metadata_path = root / DEFAULT_METADATA
    if doc_path.is_symlink() or not doc_path.is_file():
        print(f"primary context document must be a regular file before recording metadata: {DEFAULT_DOC}", file=sys.stderr)
        return 1
    if metadata_path.is_symlink():
        print(f"metadata path must not be a symlink: {DEFAULT_METADATA}", file=sys.stderr)
        return 1

    try:
        metadata = record_metadata(
            root,
            DEFAULT_DOC,
            DEFAULT_METADATA,
            args.mode,
            args.if_changed,
            args.before_hash,
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.json:
        print(safe_json_dumps(metadata))
    elif metadata.get("skipped"):
        print(f"metadata unchanged: {DEFAULT_METADATA}")
        print(f"reason: {metadata.get('reason')}")
    elif metadata.get("review_only"):
        print(f"documentation unchanged; review baseline written: {DEFAULT_METADATA}")
        print(f"source_commit: {metadata.get('source_commit_short') or metadata.get('source_commit')}")
        print(f"reviewed_commit: {metadata.get('reviewed_commit')}")
    else:
        print(f"metadata written: {DEFAULT_METADATA}")
        print(f"source_commit: {metadata.get('source_commit_short') or metadata.get('source_commit')}")
        print(f"pages: {len(metadata.get('pages', []))}")
        print(f"indexes: {len(metadata.get('indexes', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
