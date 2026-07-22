from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote


INDEX_START_MARKER = "<!-- project-context:index:start -->"
INDEX_END_MARKER = "<!-- project-context:index:end -->"
DOC_DIR = "docs/project-context"
TEMP_PLAN = f"{DOC_DIR}/_plan.md"
AREA_INDEX_GENERATOR = "project-context-index"
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
INDEX_FIELD_LIMITS = {
    "title": 80,
    "description": 160,
    "read_when": 160,
}
CONCEPT_FIELD_LIMITS = {
    "type": 40,
    **INDEX_FIELD_LIMITS,
}
AREA_TITLES = {
    "architecture": "아키텍처",
    "domains": "도메인",
    "integrations": "연동",
    "operations": "운영",
    "testing": "테스트",
    "workflows": "워크플로",
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


def set_frontmatter_field(markdown: str, key: str, value: str) -> str:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        raise ValueError("document must have YAML frontmatter before migration")
    frontmatter = match.group(0)
    field_re = re.compile(rf"(?m)^{re.escape(key)}\s*:.*$")
    replacement = f"{key}: {value}"
    if field_re.search(frontmatter):
        next_frontmatter = field_re.sub(replacement, frontmatter, count=1)
    else:
        next_frontmatter = frontmatter[:-4] + replacement + "\n---\n"
    return next_frontmatter + markdown[match.end() :]


def escape_markdown_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def area_index_for_concept(doc: str) -> str | None:
    path = PurePosixPath(doc)
    doc_dir = PurePosixPath(DOC_DIR)
    try:
        relative = path.relative_to(doc_dir)
    except ValueError:
        return None
    if len(relative.parts) != 2 or relative.name in {"index.md", "_plan.md"}:
        return None
    return (doc_dir / relative.parts[0] / "index.md").as_posix()


def wiki_inventory(
    docs: list[str],
    primary_doc: str,
    *,
    require_indexes: bool = True,
) -> dict[str, object]:
    concepts: list[str] = []
    indexes: list[str] = []
    flat_pages: list[str] = []
    errors: list[str] = []
    doc_dir = PurePosixPath(DOC_DIR)

    for doc in sorted(set(docs)):
        if doc in {primary_doc, TEMP_PLAN}:
            continue
        path = PurePosixPath(doc)
        try:
            relative = path.relative_to(doc_dir)
        except ValueError:
            errors.append(f"{doc}: context page must be under {DOC_DIR}/")
            continue
        if len(relative.parts) == 1:
            flat_pages.append(doc)
            continue
        if len(relative.parts) != 2:
            errors.append(
                f"{doc}: context navigation depth must be area/index or area/concept"
            )
            continue
        if relative.name == "index.md":
            indexes.append(doc)
        else:
            concepts.append(doc)

    expected_indexes = sorted(
        {
            area_index
            for concept in concepts
            if (area_index := area_index_for_concept(concept)) is not None
        }
    )
    if require_indexes:
        for index in sorted(set(expected_indexes) - set(indexes)):
            errors.append(f"{index}: missing area index")
        for index in sorted(set(indexes) - set(expected_indexes)):
            errors.append(f"{index}: empty area index is not allowed")
    for flat_page in flat_pages:
        errors.append(
            f"{flat_page}: legacy flat page must be migrated to {DOC_DIR}/<area>/<concept>.md"
        )

    return {
        "pages": [primary_doc, *concepts],
        "concepts": concepts,
        "indexes": indexes,
        "expected_indexes": expected_indexes,
        "flat_pages": flat_pages,
        "errors": errors,
    }


def validate_entry_fields(
    doc: str,
    fields: dict[str, str],
    limits: dict[str, int],
) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    for field, limit in limits.items():
        value = fields.get(field, "").strip()
        if not value:
            errors.append(f"{doc}: missing context metadata: {field}")
            continue
        if len(value) > limit:
            errors.append(f"{doc}: context metadata {field} exceeds {limit} characters")
            continue
        if "[" in value or "]" in value:
            errors.append(f"{doc}: context metadata {field} must be plain text")
            continue
        values[field] = value
    return values, errors


def collect_index_entries(
    root: Path,
    owner_doc: str,
    target_docs: list[str],
    *,
    concepts: bool = False,
    markdown_overrides: dict[str, str] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    entries: list[dict[str, str]] = []
    errors: list[str] = []
    owner_dir = (root / owner_doc).parent
    seen_titles: dict[str, str] = {}
    limits = CONCEPT_FIELD_LIMITS if concepts else INDEX_FIELD_LIMITS

    for doc in sorted(target_docs):
        path = root / doc
        override = (markdown_overrides or {}).get(doc)
        if override is None and (path.is_symlink() or not path.is_file()):
            errors.append(f"{doc}: context index source must be a regular file")
            continue
        markdown = (
            override
            if override is not None
            else path.read_text(encoding="utf-8", errors="replace")
        )
        fields = parse_frontmatter(markdown)
        values, field_errors = validate_entry_fields(doc, fields, limits)
        errors.extend(field_errors)
        if field_errors:
            continue
        if not concepts and fields.get("generated_by") != AREA_INDEX_GENERATOR:
            errors.append(
                f"{doc}: area index must declare generated_by: {AREA_INDEX_GENERATOR}"
            )
            continue

        if not concepts:
            normalized_title = values["title"].casefold()
            if normalized_title in seen_titles:
                errors.append(
                    f"{doc}: duplicate index title with {seen_titles[normalized_title]}: "
                    f"{values['title']}"
                )
                continue
            seen_titles[normalized_title] = doc
        relative_path = Path(os.path.relpath(path, start=owner_dir)).as_posix()
        entries.append(
            {
                "path": doc,
                "href": quote(relative_path, safe="/"),
                **values,
            }
        )
    entries.sort(key=lambda entry: (entry["title"].casefold(), entry["path"]))
    return entries, errors


def validate_unique_concept_titles(
    root: Path,
    concepts: list[str],
    markdown_overrides: dict[str, str] | None = None,
) -> list[str]:
    seen_titles: dict[str, str] = {}
    errors: list[str] = []
    for concept in sorted(concepts):
        override = (markdown_overrides or {}).get(concept)
        path = root / concept
        if override is None and (path.is_symlink() or not path.is_file()):
            continue
        markdown = (
            override
            if override is not None
            else path.read_text(encoding="utf-8", errors="replace")
        )
        title = parse_frontmatter(markdown).get("title", "").strip()
        if not title:
            continue
        normalized_title = title.casefold()
        if normalized_title in seen_titles:
            errors.append(
                f"{concept}: duplicate concept title with "
                f"{seen_titles[normalized_title]}: {title}"
            )
            continue
        seen_titles[normalized_title] = concept
    return errors


def _render_index(
    entries: list[dict[str, str]],
    *,
    heading: str,
    intro: str,
) -> str:
    lines = [INDEX_START_MARKER, f"## {heading}", "", intro, ""]
    for entry in entries:
        lines.append(
            f"- [{escape_markdown_label(entry['title'])}]({entry['href']}) — "
            f"{entry['description']}; 읽을 때: {entry['read_when']}"
        )
    lines.append(INDEX_END_MARKER)
    return "\n".join(lines)


def render_context_indexes(
    root: Path,
    primary_doc: str,
    docs: list[str],
    *,
    markdown_overrides: dict[str, str] | None = None,
) -> tuple[dict[str, str] | None, list[str]]:
    inventory = wiki_inventory(docs, primary_doc)
    errors = list(inventory["errors"])
    concepts = list(inventory["concepts"])
    indexes = list(inventory["indexes"])
    if errors:
        return None, errors
    if not concepts:
        return {}, []

    errors.extend(
        validate_unique_concept_titles(root, concepts, markdown_overrides)
    )

    home_entries, home_errors = collect_index_entries(
        root,
        primary_doc,
        indexes,
        markdown_overrides=markdown_overrides,
    )
    errors.extend(home_errors)
    rendered: dict[str, str] = {
        primary_doc: _render_index(
            home_entries,
            heading="컨텍스트 인덱스",
            intro="작업과 `읽을 때`가 맞는 영역만 연다.",
        )
    }
    for index_doc in indexes:
        area_concepts = [
            concept
            for concept in concepts
            if area_index_for_concept(concept) == index_doc
        ]
        entries, entry_errors = collect_index_entries(
            root,
            index_doc,
            area_concepts,
            concepts=True,
            markdown_overrides=markdown_overrides,
        )
        errors.extend(entry_errors)
        rendered[index_doc] = _render_index(
            entries,
            heading="개념 문서",
            intro="작업 목적과 `읽을 때`가 맞는 개념 문서만 연다.",
        )
    return (None, errors) if errors else (rendered, [])


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


def replace_or_insert_home_context_index(
    markdown: str,
    rendered_index: str,
) -> tuple[str, bool]:
    start_count = markdown.count(INDEX_START_MARKER)
    end_count = markdown.count(INDEX_END_MARKER)
    if start_count or end_count:
        return replace_context_index(markdown, rendered_index)

    evidence_heading = re.search(r"(?m)^##\s+근거\s*$", markdown)
    if evidence_heading:
        prefix = markdown[: evidence_heading.start()].rstrip()
        suffix = markdown[evidence_heading.start() :].lstrip()
        next_markdown = f"{prefix}\n\n{rendered_index}\n\n{suffix}".rstrip() + "\n"
    else:
        next_markdown = f"{markdown.rstrip()}\n\n{rendered_index}\n"
    return next_markdown, next_markdown != markdown


def remove_context_index(markdown: str) -> tuple[str, bool]:
    start_count = markdown.count(INDEX_START_MARKER)
    end_count = markdown.count(INDEX_END_MARKER)
    if start_count == end_count == 0:
        return markdown, False
    current_index, errors = extract_context_index(markdown)
    if errors or current_index is None:
        raise ValueError("; ".join(errors))
    start = markdown.find(current_index)
    end = start + len(current_index)
    parts = [
        part
        for part in (markdown[:start].rstrip(), markdown[end:].lstrip())
        if part
    ]
    next_markdown = "\n\n".join(parts).rstrip() + "\n"
    return next_markdown, next_markdown != markdown


def area_title(area: str) -> str:
    display = area.replace("-", " ").replace("_", " ").strip()
    if not display:
        return "프로젝트 영역"
    known_title = AREA_TITLES.get(display.casefold())
    if known_title:
        return known_title
    if re.search(r"[가-힣]", display):
        return display
    return f"{display} 영역"


def new_area_index_markdown(area: str) -> str:
    title = area_title(area)
    return f"""---
title: {title}
description: {title} 영역의 프로젝트 컨텍스트
read_when: {title} 관련 코드를 조사하거나 변경할 때
generated_by: {AREA_INDEX_GENERATOR}
---

# {title}

이 영역의 개념 문서를 작업 목적에 따라 선택한다.

{INDEX_START_MARKER}
{INDEX_END_MARKER}
"""
