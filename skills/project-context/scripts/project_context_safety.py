from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path


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


def resolve_commit_oid(root: Path, ref: str) -> str | None:
    try:
        output = run_git_bytes(
            root, ["rev-parse", "--verify", f"{ref.strip()}^{{commit}}"]
        )
    except ValueError:
        return None
    resolved = os.fsdecode(output.rstrip(b"\r\n"))
    return resolved or None


def canonical_commit_oid(root: Path, ref: str) -> str | None:
    candidate = ref.strip()
    resolved = resolve_commit_oid(root, candidate)
    if resolved is None or candidate.casefold() != resolved.casefold():
        return None
    return resolved


def require_expected_path(label: str, actual: str, expected: str) -> None:
    if Path(actual).as_posix() != expected:
        raise ValueError(f"{label} must be {expected}: {actual}")


def symlink_parent(root: Path, rel_path: str) -> str | None:
    current = root
    for part in Path(rel_path).parent.parts:
        current = current / part
        if current.is_symlink():
            return current.relative_to(root).as_posix()
    return None


def require_regular_file_or_missing(root: Path, rel_path: str, label: str) -> None:
    symlink = symlink_parent(root, rel_path)
    if symlink:
        raise ValueError(f"{label} parent must not be a symlink: {symlink}")
    path = root / rel_path
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {rel_path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"{label} must be a regular file or absent: {rel_path}")


def context_tree_symlinks(root: Path, rel_dir: str) -> list[str]:
    directory = root / rel_dir
    if directory.is_symlink():
        return [rel_dir]
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError(f"context document path must be a directory: {rel_dir}")
    return sorted(
        path.relative_to(root).as_posix()
        for path in directory.rglob("*")
        if path.is_symlink()
    )


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.is_file() else 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))
