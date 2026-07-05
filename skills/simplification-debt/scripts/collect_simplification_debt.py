#!/usr/bin/env python3
import argparse
import os
import re
import sys
from pathlib import Path


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".gradle",
    ".idea",
    ".next",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "vendor",
}

SKIP_SUFFIXES = {
    ".7z",
    ".avif",
    ".bin",
    ".class",
    ".db",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mov",
    ".mp4",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".webp",
    ".zip",
}

MARKER_RE = re.compile(r"(?:^|\s)(?P<prefix>#|//|--|/\*|\*|<!--)\s*ponytail:\s*(?P<body>.*)", re.IGNORECASE)


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    try:
        with path.open("rb") as f:
            chunk = f.read(4096)
    except OSError:
        return False
    return b"\0" not in chunk


def clean_body(body: str) -> str:
    body = body.strip()
    body = re.sub(r"\s*(?:\*/|-->)\s*$", "", body)
    return body.strip()


def parse_marker(body: str) -> tuple[str, str, bool]:
    body = clean_body(body)
    if "," not in body:
        return body, "", True
    ceiling, trigger = body.split(",", 1)
    ceiling = ceiling.strip()
    trigger = trigger.strip()
    return ceiling or body, trigger, not bool(trigger)


def iter_files(root: Path):
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        base = Path(current_root)
        for filename in filenames:
            path = base / filename
            if is_probably_text(path):
                yield path


def collect(root: Path):
    rows = []
    for path in iter_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        in_markdown_fence = False
        for line_number, line in enumerate(lines, start=1):
            if path.suffix.lower() in {".md", ".markdown"} and re.match(r"\s*(```|~~~)", line):
                in_markdown_fence = not in_markdown_fence
                continue
            if in_markdown_fence:
                continue
            match = MARKER_RE.search(line)
            if not match:
                continue
            ceiling, trigger, no_trigger = parse_marker(match.group("body"))
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "line": line_number,
                    "ceiling": ceiling,
                    "trigger": trigger,
                    "no_trigger": no_trigger,
                }
            )
    return rows


def render(rows) -> str:
    if not rows:
        return "No ponytail: debt. Clean ledger."

    parts = []
    current_path = None
    no_trigger_count = 0
    for row in rows:
        if row["path"] != current_path:
            if current_path is not None:
                parts.append("")
            current_path = row["path"]
            parts.append(f"{current_path}:")
        tag = " [no-trigger]" if row["no_trigger"] else ""
        if row["no_trigger"]:
            no_trigger_count += 1
        parts.append(f"  L{row['line']}: {row['ceiling']}{tag}")
        if row["trigger"]:
            parts.append(f"    trigger: {row['trigger']}")

    parts.append("")
    parts.append(f"{len(rows)} markers, {no_trigger_count} with no trigger.")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect ponytail simplification debt markers.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root to scan.")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"repo root is not a directory: {root}", file=sys.stderr)
        return 2

    print(render(collect(root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
