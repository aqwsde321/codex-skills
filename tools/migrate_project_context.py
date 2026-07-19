#!/usr/bin/env python3
"""Archive project-context artifacts and remove generated instruction blocks."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MARKERS = {
    "project-context": (
        "<!-- project-context:start -->",
        "<!-- project-context:end -->",
    ),
    "codebase-memory-mcp": (
        "<!-- codebase-memory-mcp:start -->",
        "<!-- codebase-memory-mcp:end -->",
    ),
}
ARTIFACTS = (
    (Path("docs/project-context.md"), "file"),
    (Path("docs/project-context"), "directory"),
    (Path(".codebase-memory"), "directory"),
)
INSTRUCTION_FILES = (Path("AGENTS.md"), Path("CLAUDE.md"))


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class InstructionEdit:
    path: Path
    original: str
    updated: str
    removed: dict[str, int]


@dataclass(frozen=True)
class MigrationPlan:
    root: Path
    artifacts: tuple[Path, ...]
    edits: tuple[InstructionEdit, ...]
    review_files: tuple[Path, ...]

    @property
    def changed(self):
        return bool(self.artifacts or self.edits)


def strip_marker_sections(text):
    starts = {start: name for name, (start, _) in MARKERS.items()}
    ends = {end: name for name, (_, end) in MARKERS.items()}
    output = []
    removed = Counter()
    active = None
    skip_duplicate_blank = False

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if active:
            expected_end = MARKERS[active][1]
            if stripped == expected_end:
                active = None
                skip_duplicate_blank = True
            elif stripped in starts or stripped in ends:
                raise MigrationError(f"nested or mismatched marker: {stripped}")
            continue

        if stripped in starts:
            active = starts[stripped]
            removed[active] += 1
            continue
        if stripped in ends:
            raise MigrationError(f"unmatched marker: {stripped}")

        if skip_duplicate_blank:
            if not stripped and output and not output[-1].strip():
                skip_duplicate_blank = False
                continue
            skip_duplicate_blank = False
        output.append(line)

    if active:
        raise MigrationError(f"missing marker end: {MARKERS[active][1]}")
    if skip_duplicate_blank and output and not output[-1].strip():
        output.pop()
    return "".join(output), dict(removed)


def validate_repo_root(path):
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise MigrationError(f"not a directory: {root}")
    if not (root / ".git").exists():
        raise MigrationError(f"not a Git repository root: {root}")
    return root


def has_symlink_parent(root, relative):
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            return True
    return False


def build_plan(path):
    root = validate_repo_root(path)
    artifacts = []
    for relative, expected_type in ARTIFACTS:
        candidate = root / relative
        if has_symlink_parent(root, relative) or candidate.is_symlink():
            raise MigrationError(f"refusing symlink artifact: {candidate}")
        if not candidate.exists():
            continue
        if expected_type == "file" and not candidate.is_file():
            raise MigrationError(f"expected regular file: {candidate}")
        if expected_type == "directory" and not candidate.is_dir():
            raise MigrationError(f"expected directory: {candidate}")
        artifacts.append(relative)

    edits = []
    review_files = []
    for relative in INSTRUCTION_FILES:
        candidate = root / relative
        if not candidate.exists():
            continue
        if candidate.is_symlink() or not candidate.is_file():
            raise MigrationError(f"expected regular instruction file: {candidate}")
        try:
            original = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise MigrationError(f"cannot read {candidate}: {error}") from error
        updated, removed = strip_marker_sections(original)
        if removed:
            edits.append(InstructionEdit(relative, original, updated, removed))
        if "project-context" in updated or "codebase-memory-mcp" in updated:
            review_files.append(relative)

    return MigrationPlan(root, tuple(artifacts), tuple(edits), tuple(review_files))


def default_backup_root():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path.home() / ".codex" / "backups" / "project-context" / f"{timestamp}-{os.getpid()}"


def repo_backup_path(backup_root, repo_root):
    digest = hashlib.sha256(str(repo_root).encode()).hexdigest()[:10]
    return backup_root / f"{repo_root.name}-{digest}"


def ensure_disjoint_backup(backup_root, plans):
    resolved = backup_root.expanduser().resolve()
    for plan in plans:
        try:
            resolved.relative_to(plan.root)
        except ValueError:
            pass
        else:
            raise MigrationError(f"backup must be outside repository: {resolved}")
        try:
            plan.root.relative_to(resolved)
        except ValueError:
            pass
        else:
            raise MigrationError(f"backup must not contain repository: {resolved}")
    if resolved.exists():
        raise MigrationError(f"backup path already exists: {resolved}")
    return resolved


def atomic_write(path, content):
    mode = path.stat().st_mode
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.project-context-migrate.",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def apply_plan(plan, backup_root):
    destination = repo_backup_path(backup_root, plan.root)
    destination.mkdir(parents=True, exist_ok=False)
    moved = []

    try:
        for edit in plan.edits:
            backup = destination / "instructions" / edit.path
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(plan.root / edit.path, backup)

        for relative in plan.artifacts:
            source = plan.root / relative
            backup = destination / "artifacts" / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(backup))
            moved.append((source, backup))

        for edit in plan.edits:
            atomic_write(plan.root / edit.path, edit.updated)
    except (OSError, shutil.Error):
        for edit in plan.edits:
            backup = destination / "instructions" / edit.path
            if backup.is_file():
                shutil.copy2(backup, plan.root / edit.path)
        for source, backup in reversed(moved):
            if not source.exists() and backup.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(source))
        raise

    return destination


def plan_summary(plan):
    actions = [f"archive {relative}" for relative in plan.artifacts]
    for edit in plan.edits:
        markers = ", ".join(f"{name}={count}" for name, count in sorted(edit.removed.items()))
        actions.append(f"edit {edit.path} ({markers})")
    return actions


def run(paths, apply=False, backup_root=None, output=sys.stdout):
    plans = []
    errors = []
    for path in paths:
        try:
            plans.append(build_plan(Path(path)))
        except MigrationError as error:
            errors.append(str(error))
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=output)
        return 2

    for plan in plans:
        print(f"{'APPLY' if apply else 'DRY-RUN'} {plan.root}", file=output)
        actions = plan_summary(plan)
        for action in actions:
            print(f"  - {action}", file=output)
        if not actions:
            print("  - no project-context artifacts", file=output)
        for relative in plan.review_files:
            print(f"  - REVIEW remaining reference in {relative}", file=output)

    if not apply:
        return 0

    changed = [plan for plan in plans if plan.changed]
    if not changed:
        return 0
    try:
        destination = ensure_disjoint_backup(
            Path(backup_root) if backup_root else default_backup_root(),
            changed,
        )
        destination.mkdir(parents=True)
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "repositories": []}
        for plan in changed:
            repo_backup = apply_plan(plan, destination)
            manifest["repositories"].append(
                {
                    "root": str(plan.root),
                    "backup": str(repo_backup),
                    "artifacts": [str(path) for path in plan.artifacts],
                    "instruction_files": [str(edit.path) for edit in plan.edits],
                }
            )
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (MigrationError, OSError, shutil.Error) as error:
        print(f"ERROR apply failed: {error}", file=output)
        return 2

    print(f"BACKUP {destination}", file=output)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Archive project-context artifacts and remove generated AGENTS/CLAUDE marker blocks."
    )
    parser.add_argument("repositories", nargs="*", default=["."], help="Git repository roots. Default: current directory")
    parser.add_argument("--apply", action="store_true", help="Apply the migration. Default is read-only dry-run")
    parser.add_argument("--backup-root", help="New, external backup directory. Default: ~/.codex/backups/project-context/<timestamp>")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    return run(args.repositories, apply=args.apply, backup_root=args.backup_root)


if __name__ == "__main__":
    raise SystemExit(main())
