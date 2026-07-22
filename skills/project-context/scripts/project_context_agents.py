#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_context_safety import (  # noqa: E402
    require_git_repository,
    require_regular_file_or_missing,
)


START_MARKER = "<!-- project-context:start -->"
END_MARKER = "<!-- project-context:end -->"
MARKED_SECTION_RE = re.compile(
    rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
    re.DOTALL,
)
SECTION = f"""{START_MARKER}
## Project Context

This repository has Codex-native project context documentation at `docs/project-context.md`.

Start here:

- [Project context](docs/project-context.md)

Project context includes repository overview, architecture notes, workflows, domain concepts, operations, integrations, testing guidance, and source maps.
For ordinary project questions, read the project context first and follow its links only as relevant. Read the primary page first; do not preload every supporting page. In multi-page context, open only pages whose `read_when` guidance matches the task. When context is missing, stale, ambiguous, or exact implementation verification is required, inspect the relevant source; current source remains authoritative. Follow repository instructions for code discovery. Run `$project-context` to refresh documentation only when the user explicitly requests creation or refresh, or directly invokes the skill without a narrower read-only request; missing or stale context alone does not authorize writes.
{END_MARKER}
"""


def is_semantically_current_section(section: str) -> bool:
    return (
        "docs/project-context.md" in section
        and "repository overview" in section
        and "architecture notes" in section
        and "testing guidance" in section
        and "source maps" in section
        and "follow its links" in section
        and "code discovery" in section
        and "ordinary project questions" in section
        and "do not preload every supporting page" in section
        and "read_when" in section
        and "exact implementation verification" in section
        and "current source remains authoritative" in section
        and "$project-context" in section
        and "missing or stale context alone does not authorize writes" in section
    )


def replace_sections(text: str, sections: list[re.Match]) -> tuple[str, bool]:
    parts = []
    cursor = 0
    inserted = False
    for section in sorted(sections, key=lambda match: match.start()):
        prefix = text[cursor : section.start()].rstrip()
        if prefix:
            parts.append(prefix)
        if not inserted:
            parts.append(SECTION.rstrip())
            inserted = True
        cursor = section.end()
    suffix = text[cursor:].lstrip()
    if suffix:
        parts.append(suffix)
    next_text = "\n\n".join(parts).rstrip() + "\n"
    return next_text, next_text != text


def replace_marked_section(text: str) -> tuple[str, bool]:
    marked_sections = list(MARKED_SECTION_RE.finditer(text))
    if marked_sections:
        if (
            len(marked_sections) == 1
            and is_semantically_current_section(marked_sections[0].group(0))
        ):
            return text, False
        return replace_sections(text, marked_sections)
    next_text = text.rstrip()
    if next_text:
        next_text += "\n\n"
    next_text += SECTION.rstrip() + "\n"
    return next_text, True


def ensure_file(path: Path, create_if_missing: bool) -> tuple[str, bool]:
    if path.is_symlink():
        raise ValueError(f"{path.name} must not be a symlink")
    if not path.exists():
        if not create_if_missing:
            return "skipped-missing", False
        path.write_text(SECTION, encoding="utf-8")
        return "created", True
    if not path.is_file():
        raise ValueError(f"{path.name} must be a regular file")
    text = path.read_text(encoding="utf-8", errors="replace")
    next_text, changed = replace_marked_section(text)
    if changed:
        path.write_text(next_text, encoding="utf-8")
        return "updated", True
    return "current", False


def ensure_agent_files(root: Path) -> list[dict]:
    require_git_repository(root)
    agents_path = root / "AGENTS.md"
    claude_path = root / "CLAUDE.md"
    require_regular_file_or_missing(root, "AGENTS.md", "AGENTS.md")
    require_regular_file_or_missing(root, "CLAUDE.md", "CLAUDE.md")
    create_agents = not agents_path.exists() and not claude_path.exists()
    results = []
    status, changed = ensure_file(agents_path, create_if_missing=create_agents)
    results.append({"path": "AGENTS.md", "status": status, "changed": changed})
    status, changed = ensure_file(claude_path, create_if_missing=False)
    results.append({"path": "CLAUDE.md", "status": status, "changed": changed})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure top-level agent instruction files reference project context docs.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root.")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"repo root is not a directory: {root}", file=sys.stderr)
        return 2

    try:
        results = ensure_agent_files(root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    for result in results:
        print(f"{result['path']}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
