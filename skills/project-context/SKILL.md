---
name: project-context
description: Use when setting up or starting work on a code repository so Codex can understand it faster with official codebase-memory-mcp and Codex-native project context docs; trigger for requests like "프로젝트 컨텍스트 세팅", "적용 가능하게 세팅", "Codex 문서화", "OpenWiki 대체", "codebase-memory-mcp 인덱싱", "$project-context", or when a repo needs onboarding before implementation.
---

# Project Context

## 목적

코드 repo에서 Codex가 빠르게 파악하고 작업하게 만드는 최소 절차다. 공식 `codebase-memory-mcp`는 실시간 코드 탐색/trace에 쓰고, Codex는 `docs/project-context.md`를 직접 생성/갱신해 repo 큰 그림을 남긴다.

OpenWiki와 Graphify는 기본 절차에 넣지 않는다. OpenWiki provider 비용 없이 Codex가 문서를 작성한다. Graphify는 별도 문서 repo가 커졌고 문서/PDF/회의록 사이 관계 분석이 필요할 때만 project-scoped로 적용한다.

## 빠른 판단

- 코드 작업 시작: `codebase-memory-mcp` 인덱싱을 먼저 확인한다.
- repo 설명 문서가 없거나 낡음: Codex가 `docs/project-context.md`를 생성/갱신한다.
- 실제 구현/버그 수정: `docs/project-context.md`로 큰 그림을 보고, 실제 코드 위치와 호출 관계는 MCP graph/search 도구로 확인한다.
- 문서 전용 지식그래프: Graphify를 별도 repo에서만 쓴다. 코드 repo 기본 세팅에 섞지 않는다.

## 설치 확인

먼저 도구 존재 여부를 확인한다.

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

## Repo 적용 절차

1. repo root인지 확인한다.

```bash
git rev-parse --show-toplevel
```

2. Codex-native 문서 존재 여부를 확인한다.

```bash
ls docs/project-context.md AGENTS.md README.md 2>/dev/null
```

3. Codex MCP에서 `codebase-memory-mcp` 도구를 확인하고 repo를 인덱싱/갱신한다. 도구 이름은 공식 MCP가 제공하는 이름을 우선한다. 노출된 schema가 다를 수 있으므로 `tools/list`로 확인한 뒤 호출한다.

MCP tool이 보이면 이 순서로 사용한다.

- `list_projects` 또는 `index_status`로 현재 repo가 인덱싱됐는지 확인
- 없으면 `index_repository`
- 있으면 `detect_changes`
- 변경이 있거나 stale이면 `index_repository`로 갱신

CLI가 꼭 필요할 때만 fallback으로 쓴다.

```bash
/Users/slogup/.local/bin/codebase-memory-mcp cli list_projects '{}'
```

4. `docs/project-context.md`가 없으면 생성하고, 있으면 갱신한다. 자동 생성 도구를 호출하지 말고 Codex가 직접 작성한다.

문서 작성 전 확인:

- `AGENTS.md`, `README.md`, package/build/config 파일
- `codebase-memory-mcp`의 `get_architecture`, `search_graph`, `search_code`, `trace_path`
- 최근 변경을 반영해야 하면 `git diff --stat`, `git log --oneline -5`

문서 구조:

- 목적
- 프로젝트 요약
- 기술 스택과 실행 명령
- 핵심 모듈/디렉터리
- 주요 흐름
- 작업 전 확인 지점
- 검증 방법
- 미확정 사항
- 갱신 기록

5. 문서 작성 규칙:

- 한국어로 쓴다.
- 다음 작업자가 바로 이어갈 판단, 근거, 명령, 검증만 남긴다.
- 비밀값, 토큰, private URL, 개인정보는 쓰지 않는다.
- 확인하지 못한 내용은 `확인 필요`로 표시한다.
- 기존 문서가 있으면 전체 재작성보다 stale 섹션만 갱신한다.
- 사용자가 다른 경로를 지정하지 않았으면 기본 경로는 `docs/project-context.md`다.

6. 작업 전 Codex 내부 절차:

- `docs/project-context.md`가 있으면 먼저 읽어 큰 그림을 잡는다.
- 코드 위치, 호출 관계, route, 영향 범위는 `codebase-memory-mcp` MCP 도구로 확인한다.
- MCP 결과로 후보를 좁힌 뒤 필요한 파일만 직접 읽는다.
- 추측으로 구조를 단정하지 않는다.

## 사용자에게 보고할 것

세팅 후 짧게 보고한다.

- `codebase-memory-mcp` MCP 등록 여부
- `docs/project-context.md` 생성/갱신 여부
- 확인한 주요 근거: README, AGENTS, MCP architecture/search 결과 등
- API key 또는 provider 설정이 필요 없다는 점
- 다음 작업 때 사용할 시작 프롬프트

## 시작 프롬프트 예시

```text
먼저 docs/project-context.md 문서로 프로젝트 큰 그림을 파악하고,
codebase-memory-mcp로 관련 코드 위치/호출 관계/영향 범위를 확인한 뒤 작업해.
파일을 무작정 훑지 말고 MCP 검색 결과를 근거로 필요한 파일만 읽어.
```
