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

2. 이전 성공 갱신 이후 변경 계획을 만든다. 이 계획은 LangChain OpenWiki의 `gitHead`/`updatedAt` 기반 update run을 축소한 것이다.

```bash
python3 <skill-dir>/scripts/project_context_update.py plan .
```

계획 해석:

- `recommended_action: create-docs`: context 문서가 없거나 최소 요건이 없다. 새로 만든다.
- `recommended_action: update-affected-docs`: 바뀐 source link와 연결된 문서만 갱신한다.
- `recommended_action: review-unmapped-changes`: 변경 파일이 기존 문서 근거와 직접 연결되지 않았다. 새 근거/새 섹션/무시 중 하나를 판단한다.
- `recommended_action: review-recent-history`: 이전 성공 metadata가 없다. 최근 commit evidence를 읽고 문서 기준점을 잡거나 `record`로 metadata를 생성할지 판단한다.
- `recommended_action: no-op`: 변경 없음. validate만 통과하면 문서를 건드리지 않는다.
- `affected_docs`: 갱신 후보 문서다. 정확한지 확인하되 기본적으로 이 목록을 넘지 않는다.
- `unmapped_changes`: 기존 문서가 설명하지 않는 변경이다. 새 문서가 필요한지, 기존 문서의 근거 링크를 보강할지 판단한다.
- `git status --short`, `git rev-parse HEAD`: 현재 작업트리 dirty/untracked 상태와 기준 source head를 확인한다. status 변경도 영향 계산에 포함한다.
- `git log ... --name-status --oneline`: 변경 파일뿐 아니라 커밋 단위의 의도/묶음을 확인한다. 문서 갱신 이유는 이 커밋 증거와 실제 코드 확인 둘 다로 판단한다.
- 이전 metadata는 `updatedAt`, `command`, `model`이 있는 구조적으로 유효한 경우에만 이전 성공 run 기준으로 쓴다.
- `last_update_metadata`: OpenWiki 호환 `updatedAt`, `command`, `gitHead`, `model`만 보여준다. 이 값으로 이전 run의 성격과 기준 commit을 확인한다.

3. `codebase-memory-mcp` 인덱스를 확인하고 필요하면 갱신한다. MCP tool 이름과 schema는 현재 세션의 `tools/list`를 우선한다.

- `list_projects` 또는 `index_status`로 현재 repo 인덱스 확인
- 없으면 `index_repository`
- 있으면 `detect_changes`
- 변경이 있거나 stale이면 `index_repository`

CLI fallback:

```bash
/Users/slogup/.local/bin/codebase-memory-mcp cli list_projects '{}'
```

4. high-signal context만 읽는다.

- `AGENTS.md`, `README.md`, `package.json`, `pnpm-lock.yaml`, `build.gradle`, `pom.xml`, `Cargo.toml`, `go.mod`, `pyproject.toml`, `Makefile`, `justfile`, Docker/CI/config 파일
- `.env`, private key, token, credential 파일은 읽지 않는다. 필요하면 설정 파일 존재와 non-secret setup 위치만 문서화한다.
- 기존 `docs/project-context.md`, `docs/project-context/`, README/runbook/docs tree
- `project_context_update.py plan`의 affected/unmapped 변경
- MCP `get_architecture`, `search_graph`, `search_code`, `trace_path`
- repo root에서 `**/*` 전체 훑기는 피한다. `rg --files`와 디렉터리/확장자 기준 targeted read를 쓴다.
- 기존 문서가 코드/git 증거와 충돌하면 stale 가능성을 표시하고 현재 source evidence를 우선한다.

repo가 크고 multi-agent 도구가 있으면 OpenWiki처럼 read-only 조사만 병렬화한다.

- 기본 1-2개 subagent만 쓴다. 도메인이 뚜렷하고 중형 이하일 때만 3-4개까지 늘린다.
- brief는 `기존 문서`, `runtime architecture`, `data/storage`, `UI/API surface`, `integrations`, `tests/evals`, `business workflows`처럼 좁게 나눈다.
- subagent는 읽기/요약만 한다. 파일 생성, 수정, 삭제, 이동, `docs/project-context/` 작성은 금지한다.
- subagent 결과는 내부 조사 메모로만 쓰고, 최종 문서 작성과 source 검증 책임은 메인 agent가 가진다.

5. 문서 모드를 고른다.

- 기본: 단일 문서 `docs/project-context.md`
- multi-page 조건: repo가 크거나 핵심 도메인/서비스/API 흐름이 4개 이상이면 `docs/project-context/` 하위 문서 추가
- multi-page에서도 `docs/project-context.md`는 index, 갱신 기록, 읽는 순서를 담는다.
- multi-page 문서는 서로 고립시키지 않는다. index에는 모든 하위 문서 링크를 두고, 하위 문서에는 index로 돌아가는 링크를 둔다.

6. outline을 먼저 정하고 작성한다.

OpenWiki처럼 최종 작성 전 임시 계획을 만든다.

```bash
python3 <skill-dir>/scripts/project_context_update.py write-plan .
```

`_plan.md`에는 작성/갱신할 문서, 각 문서의 source evidence, 남은 질문만 둔다. 생성된 초안을 읽고 필요한 만큼 고친다. 최종 완료 전 반드시 삭제한다.

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

7. source-grounded 규칙을 지킨다.

- 주요 주장에는 실제 repo 경로 근거를 붙인다.
- source path는 가능한 한 Markdown 링크로 쓴다: `[README.md](../README.md)`
- 모든 문서에는 `## 근거` 섹션을 두고, 해당 문서가 의존한 source path를 모은다.
- multi-page 하위 문서는 `docs/project-context.md`로 돌아가는 링크를 둔다.
- 초기 생성은 특별한 이유가 없으면 전체 8문서 이하로 유지한다.
- 얇은 문서, 스텁, source map뿐인 문서는 만들지 않는다. 넓은 문서의 heading으로 합친다.
- 절대경로, secret, private URL, credential은 쓰지 않는다.
- persistent commit hash 목록은 문서에 남기지 않는다. 특정 historical decision 설명에 꼭 필요할 때만 짧게 언급한다.
- 확인하지 못한 내용은 `확인 필요`로 표시한다.
- 파일별 inventory를 길게 나열하지 말고 작업 판단에 필요한 구조만 쓴다.
- 기존 문서가 있으면 전체 재작성보다 stale 섹션만 갱신한다.
- update run에서는 `project_context_update.py plan`의 영향 계획을 먼저 따른다. 최근 변경과 무관한 문서는 건드리지 않는다.
- 변경 source가 기존 문서 어느 곳에도 연결되지 않으면, 관련 없는 변경인지 새 문서/근거가 필요한 변경인지 판단한 뒤 기록한다.
- 커밋 메시지만 믿지 않는다. `affected_docs`/`unmapped_changes`에 나온 파일은 필요한 만큼 다시 읽고, 현재 코드가 실제로 어떻게 동작하는지 확인한 뒤 문서를 갱신한다.

8. update run은 surgical하게 한다.

- commit/dirty 변경을 먼저 읽고 `source change -> affected doc -> edit needed -> why` 형태로 짧은 내부 계획을 만든다.
- 정확한 기존 문장은 유지한다. 틀린 문장만 고친다.
- formatting-only, table reorder, wording polish만 하는 변경은 하지 않는다.
- 변경 파일이 5개 미만이면 보통 1-2개 문서만 갱신한다.
- top-level 제품 동작, setup, navigation이 바뀐 경우에만 index 문서를 크게 갱신한다.
- 이미 current면 문서를 수정하지 않고 "already current"로 보고한다.

9. top-level agent instruction 파일에 context 문서 안내를 보장한다. OpenWiki처럼 top-level 파일만 다룬다. nested `AGENTS.md`/`CLAUDE.md`는 건드리지 않는다.

```bash
python3 <skill-dir>/scripts/project_context_agents.py .
```

동작:

- `AGENTS.md`나 `CLAUDE.md`가 있으면 존재하는 top-level 파일에 안내를 보장한다.
- 둘 다 없으면 top-level `AGENTS.md`를 생성한다.
- project-context marker section이 있으면 교체한다.
- unmarked `## Project Context` 섹션이 있으면 내용이 stale하거나 다른 경로를 가리키더라도 marked 표준 section으로 교체한다.
- project-context marker section이 중복되어 있으면 하나의 표준 section으로 합친다.
- 주변 지침은 보존한다.

10. 검증하고 metadata를 기록한다.

```bash
rm -f docs/project-context/_plan.md
python3 <skill-dir>/scripts/validate_project_context.py .
python3 <skill-dir>/scripts/project_context_update.py record . --run-command update --if-changed
```

검증 기준:

- `docs/project-context.md` 존재
- `docs/project-context/.metadata.json`은 성공 갱신 후 기록
- metadata의 OpenWiki 호환 `updatedAt`, `command`, `gitHead`, `model` 구조가 유효
- metadata의 `gitHead`가 현재 git에서 조회 가능한 commit
- metadata의 `source_commit`이 있으면 `gitHead`와 같은 commit
- metadata의 `content_hash`가 volatile frontmatter, metadata, `_plan.md`를 제외한 현재 context regular file/directory snapshot과 일치
- 문서 frontmatter의 `source_commit`이 현재 git에서 조회 가능한 commit
- `## 근거` 안에 `docs/project-context` 내부 문서가 아닌 실제 repo source link가 1개 이상 존재
- 상대 Markdown source link가 실제 repo 파일/디렉터리를 가리킴
- Markdown link target에 host absolute path가 있으면 실패
- 본문이나 코드블록에 `/Users/...`, `/home/...`, `/private/...` 같은 host absolute path가 있으면 실패
- 본문에 commit hash 목록이 많으면 경고
- 모든 context 문서에 `## 근거` 섹션 존재
- multi-page index가 모든 하위 context 문서로 링크
- multi-page 하위 문서가 index 문서로 링크
- `docs/project-context/_plan.md`가 남아 있으면 실패
- 얇은 하위 문서, 짧은 single-file section directory, 8개 초과 문서는 경고
- `AGENTS.md`가 있으면 `docs/project-context.md` 안내 존재 여부 확인
- `AGENTS.md`/`CLAUDE.md`의 project-context 안내가 unmarked/stale/중복이면 경고
- 현재 HEAD와 `source_commit`이 다르면 stale 경고

metadata 기록 규칙:

- context 문서를 실제로 생성/갱신했을 때 `record`를 실행한다.
- AGENTS/CLAUDE reference만 바뀌고 context 문서 스냅샷이 그대로면 metadata를 새로 쓰지 않는다.
- no-op update면 metadata만 새로 쓰지 않는다. 이전 문서가 어떤 source 기준인지 보존한다.
- update는 이전 성공 metadata의 `gitHead`를 우선 기준으로 삼아 `git log <gitHead>..HEAD`, `git diff <gitHead>..HEAD`, `git diff HEAD`, `git status --short`를 모두 확인한다.
- update는 변경 파일을 현재 문서의 source link와 매칭해 `affected_docs`를 만들고, 매칭되지 않은 변경은 `unmapped_changes`로 둔다.
- rename이 감지되면 old path와 new path를 모두 영향 계산에 넣고 `renamed_paths`로 드러낸다.
- `affected_docs`/`unmapped_changes`의 파일은 필요한 만큼 다시 읽어 현재 코드 동작을 확인한 뒤 문서를 고친다. 커밋 메시지나 diff 목록만으로 문서를 갱신하지 않는다.
- 새 문서 생성 뒤에는 `--run-command init`, 기존 문서 갱신 뒤에는 `--run-command update`를 쓴다.
- `record --if-changed`는 실제 문서 내용 hash가 바뀐 경우에만 metadata를 쓴다.
- `record`는 `docs/project-context.md`가 없으면 실패한다.
- `record`는 `_plan.md`가 남아 있으면 실패한다.
- `record`와 `validate`는 context 문서, context 문서 디렉터리, metadata symlink를 허용하지 않는다. source-grounded 문서는 repo 안 regular file이어야 한다.
- `record`는 `docs/project-context/.metadata.json`에 OpenWiki 호환 `updatedAt`, `command`, `gitHead`, `model`과 현재 commit, 문서 목록, source link map, content hash를 저장한다.
- content hash는 `source_commit`, `updated_at` 같은 volatile frontmatter와 metadata, `_plan.md`를 제외한 context regular file/directory snapshot 기준이다.

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
