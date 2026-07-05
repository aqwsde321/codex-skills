---
name: project-context
description: Use when setting up or starting work on a code repository so Codex can understand it faster with official codebase-memory-mcp and OpenWiki; trigger for requests like "프로젝트 컨텍스트 세팅", "적용 가능하게 세팅", "OpenWiki 적용", "codebase-memory-mcp 인덱싱", "$project-context", or when a repo needs onboarding before implementation.
---

# Project Context

## 목적

코드 repo에서 Codex가 빠르게 파악하고 작업하게 만드는 최소 절차다. 공식 `codebase-memory-mcp`는 실시간 코드 탐색/trace에 쓰고, OpenWiki는 agent가 먼저 읽을 repo 문서를 만든다.

Graphify는 기본 절차에 넣지 않는다. 별도 문서 repo가 커졌고 문서/PDF/회의록 사이 관계 분석이 필요할 때만 project-scoped로 적용한다.

## 빠른 판단

- 코드 작업 시작: `codebase-memory-mcp` 인덱싱을 먼저 확인한다.
- repo 설명 문서가 없거나 낡음: OpenWiki를 초기화/업데이트한다.
- 실제 구현/버그 수정: OpenWiki로 큰 그림을 보고, 실제 코드 위치와 호출 관계는 MCP graph/search 도구로 확인한다.
- 문서 전용 지식그래프: Graphify를 별도 repo에서만 쓴다. 코드 repo 기본 세팅에 섞지 않는다.

## 설치 확인

먼저 도구 존재 여부를 확인한다.

```bash
codex mcp list
command -v openwiki
command -v codebase-memory-mcp || /Users/slogup/.local/bin/codebase-memory-mcp --version
```

기대 상태:

- `codex mcp list`에 `codebase-memory-mcp`가 enabled
- `openwiki --help` 실행 가능
- `codebase-memory-mcp`는 PATH가 아니어도 MCP config에서 절대경로로 동작 가능

설치가 없으면 공식 설치만 사용한다.

```bash
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash
npm install -g openwiki
```

## Repo 적용 절차

1. repo root에서 현재 문서 상태를 본다.

```bash
ls openwiki AGENTS.md CLAUDE.md 2>/dev/null
```

2. OpenWiki가 없으면 초기화한다.

```bash
openwiki --init
openwiki -p "Please generate concise agent documentation for this repository."
```

3. OpenWiki가 이미 있으면 갱신한다.

```bash
openwiki --update
```

4. Codex MCP에서 codebase-memory-mcp 도구를 확인하고 repo를 인덱싱한다. 도구 이름은 공식 MCP가 제공하는 이름을 우선한다. 노출된 schema가 다를 수 있으므로 `tools/list`로 확인한 뒤 호출한다.

5. 작업 전 Codex 내부 절차:

- `openwiki/`가 있으면 먼저 읽어 큰 그림을 잡는다.
- 코드 위치, 호출 관계, route, 영향 범위는 `codebase-memory-mcp` MCP 도구로 확인한다.
- MCP 결과로 후보를 좁힌 뒤 필요한 파일만 직접 읽는다.
- 추측으로 구조를 단정하지 않는다.

## 사용자에게 보고할 것

세팅 후 짧게 보고한다.

- `codebase-memory-mcp` MCP 등록 여부
- OpenWiki 생성/갱신 여부
- 생긴 파일: `openwiki/`, `AGENTS.md` 등
- API key 또는 provider 설정이 필요한 경우
- 다음 작업 때 사용할 시작 프롬프트

## 시작 프롬프트 예시

```text
먼저 openwiki/ 문서로 프로젝트 큰 그림을 파악하고,
codebase-memory-mcp로 관련 코드 위치/호출 관계/영향 범위를 확인한 뒤 작업해.
파일을 무작정 훑지 말고 MCP 검색 결과를 근거로 필요한 파일만 읽어.
```
