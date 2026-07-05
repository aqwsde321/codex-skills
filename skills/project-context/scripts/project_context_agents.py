#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path


START_MARKER = "<!-- project-context:start -->"
END_MARKER = "<!-- project-context:end -->"
PROJECT_CONTEXT_SECTION_RE = re.compile(r"^##\s+Project Context\s*$.*?(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
OPENWIKI_SECTION_RE = re.compile(r"^##\s+OpenWiki\s*$.*?(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
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
When working in this repository, read the project context first, follow its links to relevant architecture, workflow, domain, operation, and testing notes, then use `codebase-memory-mcp` for code location, call relationships, and impact analysis. If the context is stale or missing, run `$project-context` to refresh it.
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
        and "codebase-memory-mcp" in section
        and "$project-context" in section
    )


def replace_marked_section(text: str) -> tuple[str, bool]:
    marked_sections = list(MARKED_SECTION_RE.finditer(text))
    if marked_sections:
        if len(marked_sections) == 1 and is_semantically_current_section(marked_sections[0].group(0)):
            return text, False
        parts = []
        cursor = 0
        inserted = False
        for marked_section in marked_sections:
            prefix = text[cursor : marked_section.start()].rstrip()
            if prefix:
                parts.append(prefix)
            if not inserted:
                parts.append(SECTION.rstrip())
                inserted = True
            cursor = marked_section.end()
        suffix = text[cursor:].lstrip()
        if suffix:
            parts.append(suffix)
        next_text = "\n\n".join(parts).rstrip() + "\n"
        return next_text, next_text != text
    unmarked_section = PROJECT_CONTEXT_SECTION_RE.search(text)
    if unmarked_section is None:
        unmarked_section = OPENWIKI_SECTION_RE.search(text)
    if unmarked_section:
        next_text = (
            text[: unmarked_section.start()].rstrip()
            + "\n\n"
            + SECTION.rstrip()
            + "\n\n"
            + text[unmarked_section.end() :].lstrip()
        ).strip() + "\n"
        return next_text, next_text != text
    next_text = text.rstrip()
    if next_text:
        next_text += "\n\n"
    next_text += SECTION.rstrip() + "\n"
    return next_text, True


def ensure_file(path: Path, create_if_missing: bool) -> tuple[str, bool]:
    if path.is_symlink():
        return "skipped-symlink", False
    if not path.exists():
        if not create_if_missing:
            return "skipped-missing", False
        path.write_text(SECTION, encoding="utf-8")
        return "created", True
    if not path.is_file():
        return "skipped-not-file", False
    text = path.read_text(encoding="utf-8", errors="replace")
    next_text, changed = replace_marked_section(text)
    if changed:
        path.write_text(next_text, encoding="utf-8")
        return "updated", True
    return "current", False


def ensure_agent_files(root: Path) -> list[dict]:
    agents_path = root / "AGENTS.md"
    claude_path = root / "CLAUDE.md"
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

    for result in ensure_agent_files(root):
        print(f"{result['path']}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
