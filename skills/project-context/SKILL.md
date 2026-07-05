---
name: project-context
description: Use when setting up, refreshing, or starting work on a code repository so Codex can understand it faster with official codebase-memory-mcp and Codex-native source-grounded project context docs; trigger for requests like "프로젝트 컨텍스트 세팅", "적용 가능하게 세팅", "Codex 문서화", "OpenWiki 대체", "wiki 생성", "codebase-memory-mcp 인덱싱", "$project-context", or when a repo needs onboarding before implementation.
---

# Project Context

## 목적

코드 repo에서 Codex가 빠르게 파악하고 작업하게 만드는 절차다. `codebase-memory-mcp`는 코드 그래프/검색/trace를 맡고, Codex는 OpenWiki provider 없이 source-grounded wiki 문서를 직접 생성/갱신한다.

OpenWiki와 Graphify를 기본 실행하지 않는다. OpenWiki식으로 source path, freshness metadata, validation, agent instruction을 남기되 구현은 Codex 작업과 로컬 스크립트로 처리한다.

## 빠른 판단

- 새 repo 온보딩: `docs/project-context.md`를 생성한다.
- 기존 문서가 있음: 현재 HEAD, 최근 변경, 깨진 source link를 보고 stale 섹션만 갱신한다.
- repo가 크거나 docs/API/모듈이 많음: `docs/project-context.md`는 index로 두고 `docs/project-context/*.md`를 추가한다.
- 실제 구현/버그 수정: context 문서로 큰 그림을 잡고, 코드 위치/호출 관계는 `codebase-memory-mcp`로 확인한다.

## 설치 확인

```bash
codex mcp list
command -v codebase-memory-mcp || /Users/slogup/.local/bin/codebase-memory-mcp --version
```

기대 상태:

- `codex mcp list`에 `codebase-memory-mcp`가 enabled
- `codebase-memory-mcp`는 PATH가 아니어도 MCP config에서 절대경로로 동작 가능

설치가 없으면 공식 설치만 사용한다.

```bash
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash
```

## 생성/갱신 절차

1. repo root와 현재 상태를 확인한다.

```bash
git rev-parse --show-toplevel
git rev-parse --short HEAD
git status --short
ls docs/project-context.md AGENTS.md README.md 2>/dev/null
```

2. `codebase-memory-mcp` 인덱스를 확인하고 필요하면 갱신한다. MCP tool 이름과 schema는 현재 세션의 `tools/list`를 우선한다.

- `list_projects` 또는 `index_status`로 현재 repo 인덱스 확인
- 없으면 `index_repository`
- 있으면 `detect_changes`
- 변경이 있거나 stale이면 `index_repository`

CLI fallback:

```bash
/Users/slogup/.local/bin/codebase-memory-mcp cli list_projects '{}'
```

3. high-signal context만 읽는다.

- `AGENTS.md`, `README.md`, `package.json`, `pnpm-lock.yaml`, `build.gradle`, `pom.xml`, `Cargo.toml`, `go.mod`, `pyproject.toml`, `Makefile`, `justfile`, Docker/CI/config 파일
- 기존 `docs/project-context.md`와 `docs/project-context/`
- `git diff --stat`, `git log --oneline -5`
- MCP `get_architecture`, `search_graph`, `search_code`, `trace_path`

4. 문서 모드를 고른다.

- 기본: 단일 문서 `docs/project-context.md`
- multi-page 조건: repo가 크거나 핵심 도메인/서비스/API 흐름이 4개 이상이면 `docs/project-context/` 하위 문서 추가
- multi-page에서도 `docs/project-context.md`는 index, 갱신 기록, 읽는 순서를 담는다.
- multi-page 문서는 서로 고립시키지 않는다. index에는 모든 하위 문서 링크를 두고, 하위 문서에는 index로 돌아가는 링크를 둔다.

5. outline을 먼저 정하고 작성한다.

단일 문서 기본 구조:

- 목적
- 프로젝트 요약
- 기술 스택과 실행 명령
- 핵심 모듈/디렉터리
- 주요 흐름
- 작업 전 확인 지점
- 검증 방법
- 미확정 사항
- 근거
- 갱신 기록

multi-page 하위 문서 기본 구조:

- 개요
- 관련 소스
- 주요 흐름
- 작업 시 주의점
- 검증 방법
- 근거

문서 상단에 metadata를 둔다.

```yaml
---
generated_by: project-context
source_commit: <git short sha>
updated_at: <ISO-8601 UTC>
mode: single-page
---
```

6. source-grounded 규칙을 지킨다.

- 주요 주장에는 실제 repo 경로 근거를 붙인다.
- source path는 가능한 한 Markdown 링크로 쓴다: `[README.md](../README.md)`
- 모든 문서에는 `## 근거` 섹션을 두고, 해당 문서가 의존한 source path를 모은다.
- multi-page 하위 문서는 `docs/project-context.md`로 돌아가는 링크를 둔다.
- 절대경로, secret, private URL, credential은 쓰지 않는다.
- 확인하지 못한 내용은 `확인 필요`로 표시한다.
- 파일별 inventory를 길게 나열하지 말고 작업 판단에 필요한 구조만 쓴다.
- 기존 문서가 있으면 전체 재작성보다 stale 섹션만 갱신한다.

7. `AGENTS.md`에 context 문서 안내가 없으면 추가한다. 프로젝트 지침을 망가뜨리지 말고 짧은 블록만 더한다.

```markdown
## Project Context

- 작업 전 `docs/project-context.md`가 있으면 먼저 읽고 큰 그림을 잡는다.
- 코드 위치, 호출 관계, 영향 범위는 `codebase-memory-mcp`로 확인한다.
- 문서가 stale이면 `$project-context`로 갱신한다.
```

8. 검증한다.

```bash
python3 <skill-dir>/scripts/validate_project_context.py .
```

검증 기준:

- `docs/project-context.md` 존재
- metadata의 `source_commit` 존재
- 상대 Markdown source link가 1개 이상 존재
- 상대 Markdown source link가 실제 repo 파일/디렉터리를 가리킴
- 모든 context 문서에 `## 근거` 섹션 존재
- multi-page 하위 문서가 index 문서로 링크
- `AGENTS.md`가 있으면 `docs/project-context.md` 안내 존재 여부 확인
- 현재 HEAD와 `source_commit`이 다르면 stale 경고

## 작업 전 내부 절차

- `docs/project-context.md`가 있으면 먼저 읽어 큰 그림을 잡는다.
- 코드 위치, 호출 관계, route, 영향 범위는 `codebase-memory-mcp` MCP 도구로 확인한다.
- MCP 결과로 후보를 좁힌 뒤 필요한 파일만 직접 읽는다.
- 추측으로 구조를 단정하지 않는다.

## 사용자에게 보고할 것

- `codebase-memory-mcp` MCP 등록/인덱싱 여부
- `docs/project-context.md` 생성/갱신 여부
- `AGENTS.md` 안내 블록 추가 여부
- 검증 결과와 stale 여부
- API key 또는 provider 설정이 필요 없다는 점

## 시작 프롬프트 예시

```text
먼저 docs/project-context.md 문서로 프로젝트 큰 그림을 파악하고,
codebase-memory-mcp로 관련 코드 위치/호출 관계/영향 범위를 확인한 뒤 작업해.
파일을 무작정 훑지 말고 MCP 검색 결과를 근거로 필요한 파일만 읽어.
```
