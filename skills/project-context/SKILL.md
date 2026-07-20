---
name: project-context
description: Create, refresh, validate, or read source-grounded project context documentation for a code repository. Use for requests such as "프로젝트 컨텍스트 세팅", "적용 가능하게 세팅", "Codex 문서화", "wiki 생성", "프로젝트 문서 갱신", "$project-context", or when a repository needs durable onboarding context before implementation.
---

# Project Context

## 목적

코드 저장소의 큰 그림, 주요 흐름, 변경 주의점, 검증 방법을 `docs/project-context.md`와 선택적 하위 문서에 기록한다. 문서는 실제 source path와 Git 변경 근거로 생성하고 stale한 부분만 갱신한다.

이 스킬은 외부 문서화 서비스나 코드 인덱서를 설치·설정·호출하지 않는다. 코드 탐색은 저장소 `AGENTS.md`와 현재 환경에 구성된 도구 지침을 따른다.

허용 write:

- `docs/project-context.md`
- `docs/project-context/`
- top-level `AGENTS.md` 또는 `CLAUDE.md`의 marked 안내 섹션

source code는 수정하지 않는다.

## 모드 결정

- `chat`: 프로젝트 설명이나 작업 시작을 요청했지만 문서 생성을 명시하지 않았다. 기존 문서를 읽고 답한다. 파일과 metadata를 수정하지 않는다.
- `init`: context 문서가 없거나 사용자가 세팅·생성을 요청했다. 문서를 만들고 `record --mode init`으로 기록한다.
- `update`: context 문서가 있고 사용자가 갱신을 요청했거나 source 변경으로 stale하다. 영향 문서만 고치고 `record --mode update --if-changed`로 기록한다.

## Helper 명령

```bash
python3 <skill-dir>/scripts/project_context_update.py snapshot .
python3 <skill-dir>/scripts/project_context_update.py plan .
python3 <skill-dir>/scripts/project_context_update.py write-plan .
python3 <skill-dir>/scripts/project_context_update.py delete-plan .
python3 <skill-dir>/scripts/project_context_agents.py .
python3 <skill-dir>/scripts/validate_project_context.py .
python3 <skill-dir>/scripts/project_context_update.py record . --mode init|update --if-changed --before-hash <hash>
```

`plan --json`과 `write-plan --json`은 자동화용 갱신 근거를 출력한다.

## 생성·갱신 절차

### 1. 저장소 상태 확인

repo root에서 실행한다.

```bash
git rev-parse --show-toplevel
git rev-parse --short HEAD
git status --short --untracked-files=all
git log --max-count=20 --name-status --oneline
```

target repo 밖을 검색하지 않는다. `.env`, private key, token, credential 파일은 읽지 않는다. `.env.example`은 placeholder만 있을 때만 읽는다.

### 2. snapshot과 영향 계획 생성

```bash
PROJECT_CONTEXT_BEFORE_HASH="$(python3 <skill-dir>/scripts/project_context_update.py snapshot .)"
python3 <skill-dir>/scripts/project_context_update.py plan .
```

계획 해석:

- `create-docs`: 문서 생성
- `update-affected-docs`: source link가 가리키는 변경에 연결된 문서만 갱신
- `review-unmapped-changes`: 기존 문서에 연결되지 않은 변경을 새 근거·새 섹션·무시 중 하나로 판단
- `review-generated-doc-changes`: 현재 작업트리에서 context 문서가 직접 바뀌었는지 확인
- `review-recent-history`: 이전 성공 metadata가 없어 최근 history를 기준점으로 검토
- `no-op`: 문서를 수정하지 않고 검증만 수행

`affected_docs`, `unmapped_changes`, `renamed_paths`, `git_summary`, `soft_diff_budget_warnings`를 먼저 읽는다. 커밋 메시지만 믿지 말고 후보 source를 다시 확인한다.

`source_commit`은 문서가 설명하는 source 기준점이다. 이후 context 문서와 marked agent 안내만 커밋된 경우 stale로 보지 않는다.

### 3. high-signal source 조사

먼저 저장소 지침에 정의된 코드 탐색 도구를 사용한다. 후보가 좁혀지면 필요한 파일만 직접 읽는다.

우선 확인 후보:

- `AGENTS.md`, `CLAUDE.md`, `README.md`
- package/build manifest와 lockfile
- app entrypoint, route/controller, schema/migration
- tests/evals, CI, Docker, operational script
- 기존 docs, runbook, ADR
- `plan`의 affected/unmapped 파일

init에서는 최근 `git log`, 선별적 `git show`와 `git blame`으로 핵심 workflow가 생긴 이유를 확인한다. 기존 문서와 source가 충돌하면 현재 source를 우선하고 미확정 내용은 `확인 필요`로 표시한다.

큰 repo에서 read-only 병렬 조사가 도움이 되면 좁은 도메인 단위로 나눈다. 조사자는 파일을 수정하지 않는다. 최종 문서 작성과 source 검증은 메인 agent가 담당한다.

### 4. 문서 모드 선택

기본은 단일 `docs/project-context.md`다.

핵심 도메인·서비스·API 흐름이 4개 이상이거나 단일 문서가 탐색을 방해할 때만 `docs/project-context/*.md`를 추가한다. 초기 문서는 전체 8개 이하로 유지한다. tracked primary source가 10개 이하인 작은 repo는 기본 문서와 보조 문서 1~2개까지만 쓴다.

multi-page일 때:

- `docs/project-context.md`를 index와 읽는 순서로 사용
- index에서 모든 하위 문서 링크
- 하위 문서에서 index로 돌아가는 링크
- 얇은 문서와 source map 전용 문서는 더 넓은 문서 heading으로 합침

### 5. 임시 계획 작성

```bash
python3 <skill-dir>/scripts/project_context_update.py write-plan .
```

`docs/project-context/_plan.md`에 작성할 문서, source evidence, 남은 질문만 둔다. 최종 완료 전 반드시 삭제한다.

단일 문서 기본 구조:

- 목적
- 프로젝트 요약
- 기술 스택과 실행 명령
- 핵심 모듈·디렉터리
- 주요 흐름
- 작업 전 확인 지점
- 검증 방법
- 미확정 사항
- 근거
- 갱신 기록

문서 상단:

```yaml
---
generated_by: project-context
source_commit: <git short sha>
updated_at: <ISO-8601 UTC>
mode: single-page
---
```

### 6. source-grounded 작성

- 주요 주장에 실제 repo-relative Markdown source link를 붙인다.
- 구조뿐 아니라 제품·비즈니스 규칙, 존재 이유, 변경 시 판단 기준을 기록한다.
- 같은 개념은 한 canonical 섹션에 두고 다른 곳에서는 링크한다.
- 모든 context 문서에 `## 근거`와 실제 source link를 둔다.
- 절대경로, secret, private URL, credential을 쓰지 않는다.
- 파일 inventory와 commit hash 목록을 길게 남기지 않는다.
- 기존 문서의 정확한 문장은 유지하고 틀리거나 stale한 문장만 고친다.
- formatting-only, wording polish, table reorder는 하지 않는다.
- source 변경이 5개 미만이면 보통 문서 1~2개만 갱신한다.
- top-level 동작, setup, navigation이 바뀔 때만 index를 크게 수정한다.

### 7. top-level agent 안내 보장

```bash
python3 <skill-dir>/scripts/project_context_agents.py .
```

- 존재하는 top-level `AGENTS.md`와 `CLAUDE.md`만 갱신한다.
- 둘 다 없으면 top-level `AGENTS.md`를 생성한다.
- project-context marker section을 하나로 유지한다.
- unmarked `## Project Context` 섹션은 marked 표준 섹션으로 교체한다.
- nested instruction 파일은 건드리지 않는다.
- 주변 사용자 지침은 보존한다.

### 8. metadata 기록과 검증

```bash
python3 <skill-dir>/scripts/project_context_update.py delete-plan .
python3 <skill-dir>/scripts/project_context_update.py record . \
  --mode init \
  --if-changed \
  --before-hash "$PROJECT_CONTEXT_BEFORE_HASH"
python3 <skill-dir>/scripts/validate_project_context.py .
```

기존 문서 갱신은 `--mode update`를 사용한다.

metadata는 `docs/project-context/.metadata.json`에 다음 독립 필드를 기록한다.

- `generator`, `generator_version`
- `updated_at`, `run_mode`
- `source_commit`, `source_commit_short`
- `primary_doc`, `docs`, `doc_sources`
- `content_hash`

실제 문서 hash가 바뀌지 않으면 metadata를 갱신하지 않는다. agent 안내만 바뀐 경우에도 metadata를 갱신하지 않는다.

검증 기준:

- primary 문서와 required frontmatter 존재
- metadata 구조와 content hash 일치
- `source_commit`이 Git에서 조회 가능
- mode와 실제 문서 수 일치
- 모든 source link가 repo 내부 실제 경로를 가리킴
- 모든 문서에 `## 근거`와 외부 source evidence 존재
- index↔하위 문서 링크 완전
- `_plan.md` 없음
- context 문서·metadata·parent가 symlink 아님
- host absolute path와 secret-looking 값 없음
- top-level agent 안내가 하나의 current marker section

## 완료 보고

다음만 보고한다.

- `docs/project-context.md` 생성·갱신·no-op 여부
- 갱신한 하위 문서
- `AGENTS.md` 또는 `CLAUDE.md` 안내 변경 여부
- 검증 결과
- stale 또는 미확정 사항

외부 서비스, provider, API key는 필요 없다.
