#!/usr/bin/env python3
import os
import sys

if __name__ == "__main__" and not sys.flags.dont_write_bytecode:
    os.execv(sys.executable, [sys.executable, "-B", *sys.argv])

import argparse
import re
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_context_safety import (  # noqa: E402
    atomic_write_text,
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
## 프로젝트 컨텍스트

이 저장소의 Codex용 프로젝트 컨텍스트 문서는 `docs/project-context.md`에 있다.

다음 문서에서 시작한다.

- [프로젝트 컨텍스트](docs/project-context.md)

프로젝트 컨텍스트는 저장소 개요, 아키텍처, 주요 흐름, 도메인 개념, 운영, 연동, 검증 방법과 소스 근거를 담는다.
일반적인 프로젝트 질문에서는 프로젝트 컨텍스트를 먼저 읽고 필요한 링크만 따른다. 홈에서 시작해 영역 인덱스를 거치며 모든 개념 문서를 미리 읽지 않는다. 작업과 `read_when`이 맞는 문서만 연다. 컨텍스트가 없거나 오래됐거나 모호하거나 정확한 구현 확인이 필요하면 관련 소스를 확인한다. 현재 소스가 항상 우선하며 저장소의 코드 탐색 지침을 따른다. 사용자가 생성이나 갱신을 명시적으로 요청했거나 더 좁은 읽기 전용 요청 없이 `$project-context`를 직접 호출했을 때만 문서를 갱신한다. 문서가 없거나 오래됐다는 이유만으로 쓰기 권한이 생기지 않는다.
{END_MARKER}
"""


def is_semantically_current_section(section: str) -> bool:
    return section.strip() == SECTION.strip()


def marked_section(text: str) -> str | None:
    match = MARKED_SECTION_RE.search(text)
    return match.group(0) if match else None


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
        atomic_write_text(path, SECTION)
        return "created", True
    if not path.is_file():
        raise ValueError(f"{path.name} must be a regular file")
    text = path.read_text(encoding="utf-8", errors="replace")
    next_text, changed = replace_marked_section(text)
    if changed:
        atomic_write_text(path, next_text)
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
