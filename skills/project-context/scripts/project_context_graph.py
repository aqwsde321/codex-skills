from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote

from project_context_index import (
    FRONTMATTER_RE,
    INDEX_END_MARKER,
    INDEX_START_MARKER,
)
from project_context_markdown import iter_inline_links


EVIDENCE_HEADING_RE = re.compile(r"(?m)^##\s+근거\s*$")
NEXT_H2_RE = re.compile(r"(?m)^##\s+")
GENERATED_INDEX_RE = re.compile(
    rf"{re.escape(INDEX_START_MARKER)}.*?{re.escape(INDEX_END_MARKER)}",
    re.DOTALL,
)
LINK_ONLY_LINE_RE = re.compile(
    r"^\s*(?:(?:[-+*]|\d{1,9}[.)])\s+)?\[[^\]\n]+\]"
    r"\((?:[^()\n]|\([^()\n]*\))*\)\s*[.,;:]?\s*$"
)


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


def _clean_target(target: str) -> str:
    target = target.strip().split("#", 1)[0].split("?", 1)[0]
    return unquote(target).strip()


def _is_relative_target(target: str) -> bool:
    lowered = target.lower()
    return bool(target) and not (
        target.startswith("/")
        or target.startswith("#")
        or "://" in lowered
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    )


def _is_link_only_line(markdown: str, target_start: int) -> bool:
    line_start = markdown.rfind("\n", 0, target_start) + 1
    line_end = markdown.find("\n", target_start)
    if line_end == -1:
        line_end = len(markdown)
    # ponytail: only same-line prose is recognized, revisit when relationships
    # commonly use multi-line tables or definition lists.
    return LINK_ONLY_LINE_RE.fullmatch(markdown[line_start:line_end]) is not None


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
        for raw_target, target_start, _ in iter_inline_links(markdown):
            if _is_link_only_line(markdown, target_start):
                continue
            target = _clean_target(raw_target)
            if not _is_relative_target(target):
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
