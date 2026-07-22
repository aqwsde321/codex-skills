from __future__ import annotations

from pathlib import Path

from project_context_index import FRONTMATTER_RE, parse_frontmatter


TEMP_PLAN = "docs/project-context/_plan.md"
MAX_MULTI_PAGE_PRIMARY_BODY_CHARS = 4000
MAX_SINGLE_PAGE_BODY_CHARS = 4000


def assess_primary_structure(root: Path, doc_rel: str, docs: list[str]) -> list[dict]:
    doc_path = root / doc_rel
    if doc_path.is_symlink() or not doc_path.is_file():
        return []

    markdown = doc_path.read_text(encoding="utf-8", errors="replace")
    mode = parse_frontmatter(markdown).get("mode")
    context_docs = [doc for doc in docs if doc != TEMP_PLAN]
    expected_mode = (
        "multi-page" if any(doc != doc_rel for doc in context_docs) else "single-page"
    )
    if mode not in {"single-page", "multi-page"}:
        return [
            {
                "code": "invalid-primary-mode",
                "path": doc_rel,
                "message": "primary metadata mode must be single-page or multi-page",
                "actual": mode,
            }
        ]

    issues = []
    if mode != expected_mode:
        issues.append(
            {
                "code": "primary-mode-mismatch",
                "path": doc_rel,
                "message": (
                    f"metadata mode must be {expected_mode} for "
                    f"{len(context_docs)} context document(s)"
                ),
                "actual": mode,
                "expected": expected_mode,
            }
        )

    body_chars = len(FRONTMATTER_RE.sub("", markdown).strip())
    limit = (
        MAX_MULTI_PAGE_PRIMARY_BODY_CHARS
        if mode == "multi-page"
        else MAX_SINGLE_PAGE_BODY_CHARS
    )
    if body_chars > limit:
        issues.append(
            {
                "code": f"{mode}-primary-too-large",
                "path": doc_rel,
                "message": (
                    f"{mode} primary body has {body_chars} characters; limit is {limit}"
                ),
                "body_chars": body_chars,
                "limit": limit,
            }
        )

    # ponytail: semantic domain count is not mechanical, revisit when classification becomes deterministic.
    return issues
