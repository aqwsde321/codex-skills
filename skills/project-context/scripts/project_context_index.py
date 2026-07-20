from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote


INDEX_START_MARKER = "<!-- project-context:index:start -->"
INDEX_END_MARKER = "<!-- project-context:index:end -->"
TEMP_PLAN = "docs/project-context/_plan.md"
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
INDEX_FIELD_LIMITS = {
    "title": 80,
    "description": 160,
    "read_when": 160,
}


def parse_frontmatter(markdown: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(0).splitlines()[1:-1]:
        key, separator, value = line.partition(":")
        if not separator:
            continue
        fields[key.strip()] = value.strip().strip("'\"")
    return fields


def escape_markdown_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def collect_index_entries(
    root: Path,
    primary_doc: str,
    docs: list[str],
) -> tuple[list[dict[str, str]], list[str]]:
    entries: list[dict[str, str]] = []
    errors: list[str] = []
    primary_dir = (root / primary_doc).parent
    seen_titles: dict[str, str] = {}

    for doc in sorted(doc for doc in docs if doc not in {primary_doc, TEMP_PLAN}):
        path = root / doc
        if path.is_symlink() or not path.is_file():
            errors.append(f"{doc}: context index source must be a regular file")
            continue
        fields = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        values: dict[str, str] = {}
        for field, limit in INDEX_FIELD_LIMITS.items():
            value = fields.get(field, "").strip()
            if not value:
                errors.append(f"{doc}: missing index metadata: {field}")
                continue
            if len(value) > limit:
                errors.append(f"{doc}: index metadata {field} exceeds {limit} characters")
                continue
            if "[" in value or "]" in value:
                errors.append(f"{doc}: index metadata {field} must be plain text")
                continue
            values[field] = value
        if len(values) != len(INDEX_FIELD_LIMITS):
            continue

        normalized_title = values["title"].casefold()
        if normalized_title in seen_titles:
            errors.append(
                f"{doc}: duplicate index title with {seen_titles[normalized_title]}: {values['title']}"
            )
            continue
        seen_titles[normalized_title] = doc
        relative_path = Path(os.path.relpath(path, start=primary_dir)).as_posix()
        entries.append(
            {
                "path": doc,
                "href": quote(relative_path, safe="/"),
                **values,
            }
        )
    return entries, errors


def render_context_index(
    root: Path,
    primary_doc: str,
    docs: list[str],
) -> tuple[str | None, list[str]]:
    entries, errors = collect_index_entries(root, primary_doc, docs)
    if errors:
        return None, errors
    lines = [
        INDEX_START_MARKER,
        "## Context Index",
        "",
        "먼저 이 문서를 읽고, 작업과 `읽을 때`가 맞는 하위 문서만 연다.",
        "",
    ]
    for entry in entries:
        lines.append(
            f"- [{escape_markdown_label(entry['title'])}]({entry['href']}) — "
            f"{entry['description']}; 읽을 때: {entry['read_when']}"
        )
    lines.append(INDEX_END_MARKER)
    return "\n".join(lines), []


def extract_context_index(markdown: str) -> tuple[str | None, list[str]]:
    if markdown.count(INDEX_START_MARKER) != 1 or markdown.count(INDEX_END_MARKER) != 1:
        return None, ["context index must have exactly one start and end marker"]
    start = markdown.find(INDEX_START_MARKER)
    end = markdown.find(INDEX_END_MARKER)
    if start > end:
        return None, ["context index markers are out of order"]
    end += len(INDEX_END_MARKER)
    return markdown[start:end], []


def replace_context_index(markdown: str, rendered_index: str) -> tuple[str, bool]:
    current_index, errors = extract_context_index(markdown)
    if errors or current_index is None:
        raise ValueError("; ".join(errors))
    next_markdown = markdown.replace(current_index, rendered_index, 1)
    return next_markdown, next_markdown != markdown
