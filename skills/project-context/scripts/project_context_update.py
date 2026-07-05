#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote


DEFAULT_DOC = "docs/project-context.md"
DEFAULT_DOC_DIR = "docs/project-context"
DEFAULT_METADATA = "docs/project-context/.metadata.json"
GENERATOR = "project-context"
GENERATOR_VERSION = "2"
AGENT_START_MARKER = "<!-- project-context:start -->"
AGENT_END_MARKER = "<!-- project-context:end -->"
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SOURCE_COMMIT_RE = re.compile(r"^source_commit:\s*([A-Za-z0-9._/-]+)\s*$", re.MULTILINE)
VOLATILE_FRONTMATTER_RE = re.compile(r"^(source_commit|updated_at):\s*.*$", re.MULTILINE)
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
}
HIGH_SIGNAL_PREFIXES = (
    ".github/",
    ".gitlab/",
    ".circleci/",
    "docs/",
    "config/",
    "scripts/",
)


def run_git(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        return str(error)
    return "\n".join(part.strip() for part in [result.stdout, result.stderr] if part.strip())


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


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_source_commit_from_doc(root: Path, doc_rel: str) -> str | None:
    markdown = read_text(root / doc_rel)
    match = SOURCE_COMMIT_RE.search(markdown)
    return match.group(1) if match else None


def load_previous_context(root: Path, doc_rel: str, metadata_rel: str) -> tuple[str | None, str | None, str]:
    metadata = read_json(root / metadata_rel)
    if metadata:
        for key in ("source_commit", "gitHead", "git_head"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), None, metadata_rel
        for key in ("updated_at", "updatedAt"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return None, value.strip(), metadata_rel
    source_commit = read_source_commit_from_doc(root, doc_rel)
    if source_commit:
        return source_commit, None, doc_rel
    return None, None, "none"


def parse_name_status(output: str | None) -> list[dict]:
    if not output:
        return []
    rows = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            rows.append({"status": status, "path": parts[2], "old_path": parts[1]})
        elif len(parts) >= 2:
            rows.append({"status": status, "path": parts[1]})
    return rows


def collect_git_changes(
    root: Path,
    previous_commit: str | None,
    previous_updated_at: str | None,
) -> tuple[str, str, str, list[dict], str, list[dict]]:
    if previous_commit:
        commit_label = f"git log {previous_commit}..HEAD --name-status --oneline"
        commit_output = run_git(root, ["log", f"{previous_commit}..HEAD", "--name-status", "--oneline"])
        since_output = run_git(root, ["diff", "--name-status", f"{previous_commit}..HEAD"])
        since_label = f"git diff --name-status {previous_commit}..HEAD"
    elif previous_updated_at:
        commit_label = f"git log --since {previous_updated_at} --name-status --oneline"
        commit_output = run_git(root, ["log", "--since", previous_updated_at, "--name-status", "--oneline"])
        since_output = commit_output
        since_label = commit_label
    else:
        commit_label = "git log --max-count=20 --name-status --oneline"
        commit_output = run_git(root, ["log", "--max-count=20", "--name-status", "--oneline"])
        since_output = commit_output
        since_label = commit_label
    dirty_output = run_git(root, ["diff", "--name-status", "HEAD"])
    return (
        commit_label,
        commit_output,
        since_label,
        parse_name_status(since_output),
        "git diff --name-status HEAD",
        parse_name_status(dirty_output),
    )


def collect_doc_sources(root: Path, docs: list[str]) -> dict[str, list[str]]:
    source_map: dict[str, list[str]] = {}
    for doc in docs:
        doc_path = root / doc
        doc_dir = doc_path.parent
        sources: list[str] = []
        markdown = read_text(doc_path)
        for link in iter_relative_links(markdown):
            target_path = (doc_dir / link).resolve()
            try:
                rel = target_path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel.startswith("docs/project-context"):
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


def build_plan(root: Path, doc_rel: str, metadata_rel: str) -> dict:
    full_head, short_head = git_head(root)
    previous_commit, previous_updated_at, previous_source = load_previous_context(root, doc_rel, metadata_rel)
    docs = discover_docs(root, doc_rel)
    source_map = collect_doc_sources(root, docs)
    commit_label, commit_output, since_label, since_changes, dirty_label, dirty_changes = collect_git_changes(
        root,
        previous_commit,
        previous_updated_at,
    )
    changed_paths = []
    for row in [*since_changes, *dirty_changes]:
        path = row.get("path")
        if isinstance(path, str) and path not in changed_paths:
            changed_paths.append(path)
    generated_doc_changes = [path for path in changed_paths if is_generated_doc_path(path)]
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
    if not (root / doc_rel).exists():
        recommended_action = "create-docs"
    elif affected_docs:
        recommended_action = "update-affected-docs"
    elif source_change_paths:
        recommended_action = "review-unmapped-changes"
    else:
        recommended_action = "no-op"
    return {
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "current_head": full_head,
        "current_head_short": short_head,
        "previous_commit": previous_commit,
        "previous_updated_at": previous_updated_at,
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
        "source_change_paths": source_change_paths,
        "generated_doc_changes": generated_doc_changes,
        "affected_docs": affected_docs,
        "unmapped_changes": unmapped_changes,
        "recommended_action": recommended_action,
    }


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


def format_plan(plan: dict) -> str:
    lines = [
        "# Project Context Update Plan",
        "",
        f"- current_head: {plan.get('current_head_short') or plan.get('current_head') or '(unknown)'}",
        f"- previous_commit: {plan.get('previous_commit') or '(none)'}",
        f"- previous_updated_at: {plan.get('previous_updated_at') or '(none)'}",
        f"- previous_commit_source: {plan.get('previous_commit_source')}",
        f"- metadata_path: {plan.get('metadata_path')}",
        f"- recommended_action: {plan.get('recommended_action')}",
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
    ]
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
    return "\n".join(lines)


def record_metadata(root: Path, doc_rel: str, metadata_rel: str) -> dict:
    full_head, short_head = git_head(root)
    docs = discover_docs(root, doc_rel)
    source_map = collect_doc_sources(root, docs)
    metadata = {
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_commit": full_head,
        "source_commit_short": short_head,
        "primary_doc": doc_rel,
        "docs": docs,
        "doc_sources": source_map,
        "content_hash": docs_content_hash(root, docs),
    }
    metadata_path = root / metadata_rel
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(f"{json.dumps(metadata, indent=2, ensure_ascii=False)}\n", encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or record Codex-native project context updates.")
    parser.add_argument("command", choices=["plan", "record"], help="plan prints update impact; record writes metadata after docs update.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root.")
    parser.add_argument("--doc", default=DEFAULT_DOC, help=f"Primary doc path. Default: {DEFAULT_DOC}")
    parser.add_argument("--metadata", default=DEFAULT_METADATA, help=f"Metadata path. Default: {DEFAULT_METADATA}")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"repo root is not a directory: {root}", file=sys.stderr)
        return 2

    if args.command == "plan":
        plan = build_plan(root, args.doc, args.metadata)
        if args.json:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
        else:
            print(format_plan(plan))
        return 0

    metadata = record_metadata(root, args.doc, args.metadata)
    if args.json:
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
    else:
        print(f"metadata written: {args.metadata}")
        print(f"source_commit: {metadata.get('source_commit_short') or metadata.get('source_commit')}")
        print(f"docs: {len(metadata.get('docs', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
