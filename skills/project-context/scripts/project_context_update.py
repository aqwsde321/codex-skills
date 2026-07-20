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
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_context_index import (  # noqa: E402
    parse_frontmatter,
    render_context_index,
    replace_context_index,
)
from project_context_markdown import iter_inline_link_targets  # noqa: E402


DEFAULT_DOC = "docs/project-context.md"
DEFAULT_DOC_DIR = "docs/project-context"
DEFAULT_METADATA = "docs/project-context/.metadata.json"
DEFAULT_TEMP_PLAN = "docs/project-context/_plan.md"
SNAPSHOT_EXCLUDED_PATHS = {DEFAULT_METADATA, DEFAULT_TEMP_PLAN}
GENERATOR = "project-context"
GENERATOR_VERSION = "20"
AGENT_START_MARKER = "<!-- project-context:start -->"
AGENT_END_MARKER = "<!-- project-context:end -->"
SOURCE_COMMIT_RE = re.compile(r"^source_commit:\s*([A-Za-z0-9._/-]+)\s*$", re.MULTILINE)
PROJECT_CONTEXT_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
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


def run_git_bytes(root: Path, args: list[str]) -> bytes:
    try:
        result = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise ValueError(f"git command failed: {error}") from error
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip() or "unknown git error"
        raise ValueError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def require_git_repository(root: Path) -> None:
    top_level = os.fsdecode(
        run_git_bytes(root, ["rev-parse", "--show-toplevel"]).rstrip(b"\r\n")
    )
    if Path(top_level).resolve() != root.resolve():
        raise ValueError(f"repo root must be the Git top-level directory: {top_level}")
    run_git_bytes(root, ["rev-parse", "--verify", "HEAD^{commit}"])


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


def git_commit_exists(root: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "--no-pager", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode == 0


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


def clean_target(target: str) -> str:
    target = target.strip()
    target = target.split("#", 1)[0]
    target = target.split("?", 1)[0]
    return unquote(target).strip()


def is_external_target(target: str) -> bool:
    lowered = target.lower()
    return (
        "://" in lowered
        or lowered.startswith("#")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    )


def iter_relative_links(markdown: str):
    for raw_target in iter_inline_link_targets(markdown):
        target = clean_target(raw_target)
        if not target or is_external_target(target) or target.startswith("/"):
            continue
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


def is_structured_update_metadata(metadata: dict) -> bool:
    updated_at = metadata.get("updated_at")
    return (
        isinstance(updated_at, str)
        and PROJECT_CONTEXT_TIMESTAMP_RE.fullmatch(updated_at) is not None
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
    markdown = read_text(doc_path)
    match = SOURCE_COMMIT_RE.search(markdown)
    return match.group(1) if match else None


def load_previous_context(root: Path, doc_rel: str, metadata_rel: str) -> tuple[str | None, str | None, str]:
    metadata_updated_at = None
    if not symlink_parent(root, metadata_rel):
        metadata = read_json(root / metadata_rel)
        if metadata and is_structured_update_metadata(metadata):
            source_commit = metadata.get("source_commit")
            valid_source_commit = (
                source_commit.strip()
                if isinstance(source_commit, str)
                and source_commit.strip()
                and git_commit_exists(root, source_commit.strip())
                else None
            )
            reviewed_commit = metadata.get("reviewed_commit")
            valid_reviewed_commit = (
                reviewed_commit.strip()
                if isinstance(reviewed_commit, str)
                and reviewed_commit.strip()
                and git_commit_exists(root, reviewed_commit.strip())
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
    if source_commit and git_commit_exists(root, source_commit):
        return source_commit, None, doc_rel
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
    doc_path = root / doc_rel
    if doc_path.is_symlink() or not doc_path.is_file():
        return False
    markdown = read_text(doc_path)
    if parse_frontmatter(markdown).get("mode") != "multi-page":
        return False
    rendered_index, errors = render_context_index(root, doc_rel, docs)
    if errors or rendered_index is None:
        return True
    try:
        _, changed = replace_context_index(markdown, rendered_index)
    except ValueError:
        return True
    return changed


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
    source_map = collect_doc_sources(root, docs)
    current_content_hash = docs_content_hash(root, docs)
    persisted_metadata = read_json(root / metadata_rel)
    metadata_document_state_stale = not persisted_metadata or any(
        persisted_metadata.get(field) != expected
        for field, expected in {
            "primary_doc": doc_rel,
            "docs": docs,
            "doc_sources": source_map,
            "content_hash": current_content_hash,
        }.items()
    )
    context_index_stale = context_index_needs_sync(root, doc_rel, docs)
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
    affected_docs, unmapped_changes = map_affected_docs(
        docs,
        source_map,
        source_change_paths,
        doc_rel,
        root,
        previous_commit,
    )
    budget_warnings = soft_diff_budget_warnings(source_change_paths, affected_docs, doc_rel)
    if not (root / doc_rel).exists():
        recommended_action = "create-docs"
    elif affected_docs:
        recommended_action = "update-affected-docs"
    elif source_change_paths:
        recommended_action = "review-unmapped-changes"
    elif generated_context_doc_changes:
        recommended_action = "review-generated-doc-changes"
    elif not has_previous_context and since_changes:
        recommended_action = "review-recent-history"
    else:
        recommended_action = "no-op"
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
        "doc_sources": source_map,
        "commit_evidence_label": commit_label,
        "commit_evidence": commit_output,
        "since_changes_label": since_label,
        "since_changes": since_changes,
        "dirty_changes_label": dirty_label,
        "dirty_changes": dirty_changes,
        "renamed_paths": renamed_paths,
        "source_change_paths": source_change_paths,
        "generated_doc_changes": generated_doc_changes,
        "generated_context_doc_changes": generated_context_doc_changes,
        "metadata_document_state_stale": metadata_document_state_stale,
        "context_index_stale": context_index_stale,
        "affected_docs": affected_docs,
        "unmapped_changes": unmapped_changes,
        "soft_diff_budget_warning": "; ".join(budget_warnings) if budget_warnings else None,
        "soft_diff_budget_warnings": budget_warnings,
        "recommended_action": recommended_action,
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


def format_plan(plan: dict) -> str:
    lines = [
        "# Project Context Update Plan",
        "",
        f"- current_head: {plan.get('current_head_short') or plan.get('current_head') or '(unknown)'}",
        f"- previous_commit: {plan.get('previous_commit') or '(none)'}",
        f"- previous_updated_at: {plan.get('previous_updated_at') or '(none)'}",
        f"- previous_commit_source: {plan.get('previous_commit_source')}",
        f"- metadata_path: {plan.get('metadata_path')}",
        f"- last_update_metadata_source: {plan.get('last_update_metadata_source') or '(none)'}",
        f"- recommended_action: {plan.get('recommended_action')}",
        f"- missing_last_update_warning: {plan.get('missing_last_update_warning') or '(none)'}",
        f"- soft_diff_budget_warning: {plan.get('soft_diff_budget_warning') or '(none)'}",
        "",
        "## Soft Diff Budget Warnings",
    ]
    budget_warnings = plan.get("soft_diff_budget_warnings", [])
    if budget_warnings:
        lines.extend(f"- {warning}" for warning in budget_warnings)
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "## Project Context Git Summary",
        "",
        *format_block(plan.get("git_summary")),
        "",
        "## Last Update Metadata",
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
        "## Docs Inventory",
    ])
    doc_sources = plan.get("doc_sources", {})
    for doc in plan.get("docs", []):
        sources = doc_sources.get(doc, [])
        lines.append(f"- {doc}")
        if sources:
            for source in sources:
                lines.append(f"  - source: {source}")
        else:
            lines.append("  - source: (none)")
    lines.extend(["", "## Affected Docs"])
    affected_docs = plan.get("affected_docs", {})
    if affected_docs:
        for doc, paths in affected_docs.items():
            lines.append(f"- {doc}")
            for path in paths:
                lines.append(f"  - changed: {path}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## Unmapped Changes"])
    unmapped = plan.get("unmapped_changes", [])
    if unmapped:
        lines.extend(f"- {path}" for path in unmapped)
    else:
        lines.append("- (none)")
    lines.extend(["", "## Generated Doc Changes"])
    generated_doc_changes = plan.get("generated_doc_changes", [])
    if generated_doc_changes:
        lines.extend(f"- {path}" for path in generated_doc_changes)
    else:
        lines.append("- (none)")
    lines.extend(["", "## Generated Context Doc Changes"])
    generated_context_doc_changes = plan.get("generated_context_doc_changes", [])
    if generated_context_doc_changes:
        lines.extend(f"- {path}" for path in generated_context_doc_changes)
    else:
        lines.append("- (none)")
    lines.extend(["", "## Renamed Paths"])
    renamed_paths = plan.get("renamed_paths", [])
    if renamed_paths:
        for renamed_path in renamed_paths:
            lines.append(f"- {renamed_path.get('old_path')} -> {renamed_path.get('path')}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)


def format_temp_plan(plan: dict) -> str:
    lines = [
        "# Project Context Draft Plan",
        "",
        "Delete this file before finishing the project-context run.",
        "",
        "## Run Summary",
        "",
        f"- current_head: {plan.get('current_head_short') or plan.get('current_head') or '(unknown)'}",
        f"- previous_commit: {plan.get('previous_commit') or '(none)'}",
        f"- previous_updated_at: {plan.get('previous_updated_at') or '(none)'}",
        f"- recommended_action: {plan.get('recommended_action')}",
        f"- missing_last_update_warning: {plan.get('missing_last_update_warning') or '(none)'}",
        f"- soft_diff_budget_warning: {plan.get('soft_diff_budget_warning') or '(none)'}",
        f"- last_update_metadata_source: {plan.get('last_update_metadata_source') or '(none)'}",
        "",
        "## Project Context Git Summary",
        "",
        *format_block(plan.get("git_summary")),
        "",
        "## Last Update Metadata",
        "",
        *format_json_block(plan.get("last_update_metadata")),
        "",
        "## Soft Diff Budget Warnings",
        "",
    ]
    budget_warnings = plan.get("soft_diff_budget_warnings", [])
    if budget_warnings:
        lines.extend(f"- {warning}" for warning in budget_warnings)
    else:
        lines.append("- (none)")

    lines.extend([
        "",
        "## Intended Docs",
        "",
    ])
    for doc in plan.get("docs", []):
        lines.append(f"- {doc}")
    if not plan.get("docs"):
        lines.append("- docs/project-context.md")

    lines.extend(["", "## Docs Impact Plan", ""])
    affected_docs = plan.get("affected_docs", {})
    if affected_docs:
        for doc, paths in affected_docs.items():
            lines.append(f"- doc: {doc}")
            for path in paths:
                lines.append(f"  - source change: {path}")
                lines.append("    - edit needed: confirm changed behavior and update only stale claims")
                lines.append("    - why: linked source changed since the previous successful run")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Unmapped Changes", ""])
    unmapped = plan.get("unmapped_changes", [])
    if unmapped:
        for path in unmapped:
            lines.append(f"- source change: {path}")
            lines.append("  - docs affected: confirm whether a new section/source link is needed")
            lines.append("  - why: no existing context doc links to this source")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Generated Context Doc Changes", ""])
    generated_context_doc_changes = plan.get("generated_context_doc_changes", [])
    if generated_context_doc_changes:
        for path in generated_context_doc_changes:
            lines.append(f"- context doc change: {path}")
            lines.append("  - action: verify whether the local doc edit is intended, stale, or should be recorded")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Renamed Paths", ""])
    renamed_paths = plan.get("renamed_paths", [])
    if renamed_paths:
        for renamed_path in renamed_paths:
            lines.append(f"- {renamed_path.get('old_path')} -> {renamed_path.get('path')}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Evidence-backed Relationships", ""])
    lines.append("- (none yet; for 3+ supporting pages use: source concept -> relationship meaning -> target concept)")

    lines.extend(["", "## Deferred Coverage", ""])
    lines.append("- (none yet; record any page-budget deferral with area, source anchor, and reason)")

    lines.extend(["", "## Source Evidence", ""])
    doc_sources = plan.get("doc_sources", {})
    if doc_sources:
        for doc, sources in doc_sources.items():
            lines.append(f"- {doc}")
            if sources:
                for source in sources:
                    lines.append(f"  - {source}")
            else:
                lines.append("  - (none yet)")
    else:
        lines.append("- (none yet)")

    lines.extend(["", "## Remaining Questions", "", "- (none yet)"])
    return "\n".join(lines) + "\n"


def write_temp_plan(root: Path, plan_rel: str, plan: dict) -> Path:
    symlink = symlink_parent(root, plan_rel)
    if symlink:
        raise ValueError(f"temporary plan parent must not be a symlink: {symlink}")
    plan_path = root / plan_rel
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(format_temp_plan(plan), encoding="utf-8")
    return plan_path


def delete_temp_plan(root: Path, plan_rel: str) -> tuple[str, bool]:
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
    plan_path.unlink()
    return f"temporary plan deleted: {plan_rel}", True


def sync_context_index(root: Path, doc_rel: str) -> dict:
    doc_path = root / doc_rel
    if doc_path.is_symlink() or not doc_path.is_file():
        raise ValueError(f"primary context document must be a regular file: {doc_rel}")
    markdown = read_text(doc_path)
    if parse_frontmatter(markdown).get("mode") != "multi-page":
        return {
            "changed": False,
            "skipped": True,
            "reason": "primary document is not in multi-page mode",
            "doc": doc_rel,
        }
    docs = [doc for doc in discover_docs(root, doc_rel) if doc != DEFAULT_TEMP_PLAN]
    rendered_index, errors = render_context_index(root, doc_rel, docs)
    if errors or rendered_index is None:
        raise ValueError("\n".join(errors))
    next_markdown, changed = replace_context_index(markdown, rendered_index)
    if changed:
        doc_path.write_text(next_markdown, encoding="utf-8")
    return {
        "changed": changed,
        "skipped": False,
        "doc": doc_rel,
        "supporting_docs": len(docs) - 1,
    }


def record_metadata(
    root: Path,
    doc_rel: str,
    metadata_rel: str,
    run_mode: str,
    if_changed: bool,
    before_hash: str | None,
) -> dict:
    require_git_repository(root)
    full_head, short_head = git_head(root)
    docs = discover_docs(root, doc_rel)
    source_map = collect_doc_sources(root, docs)
    content_hash = docs_content_hash(root, docs)
    previous_metadata = read_json(root / metadata_rel) or {}
    docs_unchanged = if_changed and (
        (bool(before_hash) and before_hash == content_hash)
        or previous_metadata.get("content_hash") == content_hash
    )
    previous_source_commit = previous_metadata.get("source_commit")
    valid_previous_source_commit = (
        previous_source_commit.strip()
        if isinstance(previous_source_commit, str)
        and previous_source_commit.strip()
        and git_commit_exists(root, previous_source_commit.strip())
        else None
    )
    document_source_ref = read_source_commit_from_doc(root, doc_rel)
    valid_document_source_commit = (
        git_output(root, ["rev-parse", document_source_ref])
        if document_source_ref and git_commit_exists(root, document_source_ref)
        else None
    )
    review_source_commit = valid_document_source_commit or valid_previous_source_commit
    previous_reviewed_commit = previous_metadata.get("reviewed_commit")
    valid_previous_reviewed_commit = (
        previous_reviewed_commit.strip()
        if isinstance(previous_reviewed_commit, str)
        and previous_reviewed_commit.strip()
        and review_source_commit
        and git_commit_exists(root, previous_reviewed_commit.strip())
        and git_commit_is_ancestor(root, review_source_commit, previous_reviewed_commit.strip())
        and git_commit_is_ancestor(root, previous_reviewed_commit.strip(), "HEAD")
        else None
    )
    previous_source_commit_short = previous_metadata.get("source_commit_short")
    resolved_previous_source_commit_short = (
        git_output(root, ["rev-parse", previous_source_commit_short.strip()])
        if isinstance(previous_source_commit_short, str)
        and previous_source_commit_short.strip()
        and git_commit_exists(root, previous_source_commit_short.strip())
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
        "primary_doc": doc_rel,
        "docs": docs,
        "doc_sources": source_map,
        "content_hash": content_hash,
    }
    previous_updated_at = previous_metadata.get("updated_at")
    metadata_needs_rewrite = (
        valid_previous_reviewed_commit is None
        or source_metadata_needs_repair
        or not isinstance(previous_updated_at, str)
        or PROJECT_CONTEXT_TIMESTAMP_RE.fullmatch(previous_updated_at) is None
        or previous_metadata.get("run_mode") not in {"init", "update"}
        or any(
            previous_metadata.get(field) != expected
            for field, expected in expected_derived_metadata.items()
        )
    )

    if docs_unchanged and not metadata_needs_rewrite and not committed_source_changes:
        return {
            "skipped": True,
            "reason": "documentation unchanged and no committed source review baseline to advance",
            "metadata_path": metadata_rel,
            "source_commit": previous_metadata.get("source_commit"),
            "source_commit_short": previous_metadata.get("source_commit_short"),
            "reviewed_commit": previous_metadata.get("reviewed_commit"),
            "docs": docs,
            "content_hash": content_hash,
        }

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

    metadata = {
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "updated_at": updated_at,
        "run_mode": run_mode,
        "source_commit": source_commit,
        "source_commit_short": source_commit_short,
        "reviewed_commit": full_head,
        "primary_doc": doc_rel,
        "docs": docs,
        "doc_sources": source_map,
        "content_hash": content_hash,
    }
    metadata_path = root / metadata_rel
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(f"{safe_json_dumps(metadata)}\n", encoding="utf-8")
    return {**metadata, "review_only": True} if docs_unchanged else metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or record Codex-native project context updates.")
    parser.add_argument("command", choices=["plan", "write-plan", "delete-plan", "sync-index", "snapshot", "record"], help="plan prints update impact; write-plan creates a temporary docs plan; delete-plan removes the temporary plan safely; sync-index refreshes the deterministic multi-page router; snapshot prints the current docs content hash; record writes metadata after docs update.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root.")
    parser.add_argument("--doc", default=DEFAULT_DOC, help=f"Primary doc path. Default: {DEFAULT_DOC}")
    parser.add_argument("--metadata", default=DEFAULT_METADATA, help=f"Metadata path. Default: {DEFAULT_METADATA}")
    parser.add_argument("--plan-path", default=DEFAULT_TEMP_PLAN, help=f"Temporary draft plan path. Default: {DEFAULT_TEMP_PLAN}")
    parser.add_argument("--mode", choices=["init", "update"], default="update", help="Project context run mode stored in metadata.")
    parser.add_argument("--if-changed", action="store_true", help="Preserve the documentation source commit when docs are unchanged while recording newly reviewed commits.")
    parser.add_argument("--before-hash", help="Docs content hash captured before the run. With --if-changed, metadata is skipped when it still matches.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"repo root is not a directory: {root}", file=sys.stderr)
        return 2
    for label, value in (
        ("--doc", args.doc),
        ("--metadata", args.metadata),
        ("--plan-path", args.plan_path),
    ):
        path_error = validate_repo_path(root, label, value)
        if path_error:
            print(path_error, file=sys.stderr)
            return 2
    try:
        require_git_repository(root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.command in {"plan", "write-plan"}:
        plan = build_plan(root, args.doc, args.metadata)
        if args.command == "write-plan":
            if (root / args.plan_path).is_symlink():
                print(f"temporary plan path must not be a symlink: {args.plan_path}", file=sys.stderr)
                return 1
            try:
                plan_path = write_temp_plan(root, args.plan_path, plan)
            except ValueError as error:
                print(str(error), file=sys.stderr)
                return 1
            if args.json:
                print(safe_json_dumps(
                    {
                        "plan_path": args.plan_path,
                        "recommended_action": plan.get("recommended_action"),
                        "previous_commit": plan.get("previous_commit"),
                        "previous_updated_at": plan.get("previous_updated_at"),
                        "previous_commit_source": plan.get("previous_commit_source"),
                        "last_update_metadata": plan.get("last_update_metadata"),
                        "last_update_metadata_source": plan.get("last_update_metadata_source"),
                        "docs": plan.get("docs", []),
                        "missing_last_update_warning": plan.get("missing_last_update_warning"),
                        "soft_diff_budget_warning": plan.get("soft_diff_budget_warning"),
                        "soft_diff_budget_warnings": plan.get("soft_diff_budget_warnings", []),
                        "git_summary": plan.get("git_summary"),
                        "source_change_paths": plan.get("source_change_paths", []),
                        "affected_docs": plan.get("affected_docs", {}),
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
            message, deleted = delete_temp_plan(root, args.plan_path)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.json:
            print(safe_json_dumps({"plan_path": args.plan_path, "deleted": deleted}))
        else:
            print(message)
        return 0

    if args.command == "sync-index":
        try:
            result = sync_context_index(root, args.doc)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.json:
            print(safe_json_dumps(result))
        elif result.get("skipped"):
            print(f"context index unchanged: {result.get('reason')}")
        else:
            state = "updated" if result.get("changed") else "current"
            print(f"context index {state}: {args.doc}")
            print(f"supporting docs: {result.get('supporting_docs')}")
        return 0

    if args.command == "snapshot":
        docs = discover_docs(root, args.doc)
        content_hash = docs_content_hash(root, docs)
        if args.json:
            print(safe_json_dumps({"content_hash": content_hash, "docs": docs}))
        else:
            print(content_hash)
        return 0

    plan_path = root / args.plan_path
    if plan_path.exists() or plan_path.is_symlink():
        print(f"temporary plan must be deleted before recording metadata: {args.plan_path}", file=sys.stderr)
        return 1
    doc_path = root / args.doc
    metadata_path = root / args.metadata
    if doc_path.is_symlink() or not doc_path.is_file():
        print(f"primary context document must be a regular file before recording metadata: {args.doc}", file=sys.stderr)
        return 1
    if metadata_path.is_symlink():
        print(f"metadata path must not be a symlink: {args.metadata}", file=sys.stderr)
        return 1

    metadata = record_metadata(root, args.doc, args.metadata, args.mode, args.if_changed, args.before_hash)
    if args.json:
        print(safe_json_dumps(metadata))
    elif metadata.get("skipped"):
        print(f"metadata unchanged: {args.metadata}")
        print(f"reason: {metadata.get('reason')}")
    elif metadata.get("review_only"):
        print(f"documentation unchanged; review baseline written: {args.metadata}")
        print(f"source_commit: {metadata.get('source_commit_short') or metadata.get('source_commit')}")
        print(f"reviewed_commit: {metadata.get('reviewed_commit')}")
    else:
        print(f"metadata written: {args.metadata}")
        print(f"source_commit: {metadata.get('source_commit_short') or metadata.get('source_commit')}")
        print(f"docs: {len(metadata.get('docs', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
