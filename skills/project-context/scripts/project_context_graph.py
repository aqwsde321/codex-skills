from __future__ import annotations

import hashlib
import re
from pathlib import Path

from project_context_index import (
    FRONTMATTER_RE,
    INDEX_END_MARKER,
    INDEX_START_MARKER,
)
from project_context_markdown import (
    iter_inline_links_with_spans,
    relative_link_target,
)


EVIDENCE_HEADING_RE = re.compile(r"(?m)^##\s+근거\s*$")
NEXT_H2_RE = re.compile(r"(?m)^##\s+")
GENERATED_INDEX_RE = re.compile(
    rf"{re.escape(INDEX_START_MARKER)}.*?{re.escape(INDEX_END_MARKER)}",
    re.DOTALL,
)
LIST_PREFIX_RE = re.compile(r"^\s*(?:(?:[-+*]|\d{1,9}[.)])\s+)?")
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>\n]*>")
NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)


def page_content_hashes(root: Path, pages: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for page in pages:
        path = root / page
        if path.is_symlink() or not path.is_file():
            continue
        hashes[page] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def semantic_markdown(markdown: str) -> str:
    body = FRONTMATTER_RE.sub("", markdown, count=1)
    body = GENERATED_INDEX_RE.sub("", body)
    evidence = EVIDENCE_HEADING_RE.search(body)
    if evidence:
        next_heading = NEXT_H2_RE.search(body, evidence.end())
        end = next_heading.start() if next_heading else len(body)
        body = body[: evidence.start()] + body[end:]
    return body


def _relationship_prose_lines(
    markdown: str,
    links: list[tuple[str, int, int, int, int]],
) -> set[int]:
    spans_by_line: dict[int, tuple[int, list[tuple[int, int]]]] = {}
    for _, target_start, _, link_start, link_end in links:
        line_start = markdown.rfind("\n", 0, target_start) + 1
        line_end = markdown.find("\n", target_start)
        if line_end == -1:
            line_end = len(markdown)
        if link_start < line_start or link_end > line_end:
            continue
        _, spans = spans_by_line.setdefault(line_start, (line_end, []))
        spans.append((link_start, link_end))

    prose_lines: set[int] = set()
    for line_start, (line_end, spans) in spans_by_line.items():
        remaining = markdown[line_start:line_end]
        for link_start, link_end in sorted(spans, reverse=True):
            start = link_start - line_start
            end = link_end - line_start
            remaining = remaining[:start] + remaining[end:]
        remaining = LIST_PREFIX_RE.sub("", remaining, count=1)
        remaining = HTML_TAG_RE.sub("", remaining)
        if NON_WORD_RE.sub("", remaining):
            prose_lines.add(line_start)
    # ponytail: only same-line prose is recognized, revisit when relationships
    # commonly use multi-line tables or definition lists.
    return prose_lines


def collect_semantic_relationships(
    root: Path,
    concepts: list[str],
) -> dict[str, dict[str, list[str]]]:
    concept_set = set(concepts)
    outgoing: dict[str, set[str]] = {concept: set() for concept in concepts}
    incoming: dict[str, set[str]] = {concept: set() for concept in concepts}

    for concept in concepts:
        path = root / concept
        if path.is_symlink() or not path.is_file():
            continue
        markdown = semantic_markdown(
            path.read_text(encoding="utf-8", errors="replace")
        )
        links = list(iter_inline_links_with_spans(markdown))
        prose_lines = _relationship_prose_lines(markdown, links)
        for raw_target, target_start, _, _, _ in links:
            line_start = markdown.rfind("\n", 0, target_start) + 1
            if line_start not in prose_lines:
                continue
            target = relative_link_target(raw_target)
            if target is None:
                continue
            target_path = (path.parent / target).resolve()
            try:
                target_rel = target_path.relative_to(root).as_posix()
            except ValueError:
                continue
            if target_rel not in concept_set or target_rel == concept:
                continue
            outgoing[concept].add(target_rel)
            incoming[target_rel].add(concept)

    neighbors = {
        concept: sorted(outgoing[concept] | incoming[concept])
        for concept in concepts
    }
    return {
        "outgoing": {
            concept: sorted(targets) for concept, targets in outgoing.items()
        },
        "incoming": {
            concept: sorted(sources) for concept, sources in incoming.items()
        },
        "neighbors": neighbors,
    }
