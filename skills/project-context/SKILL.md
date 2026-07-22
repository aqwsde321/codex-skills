---
name: project-context
description: Read existing or explicitly create, refresh, and validate source-grounded project context documentation for a code repository. Use when the user asks for repository project context, "프로젝트 컨텍스트 세팅", "프로젝트 컨텍스트 wiki 생성", "프로젝트 컨텍스트 문서 갱신", or invokes "$project-context". Do not trigger for ordinary implementation, debugging, or review merely because onboarding docs are missing.
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

write gate: 사용자가 프로젝트 컨텍스트 문서 생성·세팅·갱신을 명시했거나, 더 좁은 read-only 요청 없이 `$project-context`를 직접 실행한 경우에만 `init` 또는 `update`를 허용한다. 문서 부재·stale 또는 일반 구현·디버깅·리뷰 요청만으로 write하지 않는다.

- `chat`: write gate를 충족하지 않았다. 문서가 없어도 만들지 않는다. primary만 먼저 읽고, multi-page이면 작업과 `read_when`이 맞는 하위 문서만 연다. 모든 하위 문서를 미리 읽지 않는다. 문서로 충분하면 광범위한 source 재탐색 없이 답한다. 정확한 최신 동작 확인이 필요하거나 context가 stale·모호·source와 충돌할 때만 관련 source를 좁게 확인한다. 충돌 시 현재 source가 우선이다. 파일과 metadata를 수정하지 않는다.
- `init`: write gate를 충족했고 context 문서가 없다. 문서를 만들고 `record --mode init`으로 기록한다.
- `update`: write gate를 충족했고 context 문서가 있다. 영향 문서와 계획이 요구한 문서 구조만 고치고 `record --mode update --if-changed`로 기록한다.

## Helper 명령

```bash
python3 <skill-dir>/scripts/project_context_update.py snapshot .
python3 <skill-dir>/scripts/project_context_update.py plan .
python3 <skill-dir>/scripts/project_context_update.py write-plan .
python3 <skill-dir>/scripts/project_context_update.py delete-plan .
python3 <skill-dir>/scripts/project_context_update.py sync-index .
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
- `review-document-structure`: 현재 mode·문서 수·primary body budget을 재검토하고 필요한 분할·병합 수행
- `review-recent-history`: 이전 성공 metadata가 없어 최근 history를 기준점으로 검토
- `no-op`: 문서는 수정하지 않는다. 변경 후 되돌린 commit까지 검토 기준점에 포함되도록 `record --if-changed`를 실행한 뒤 검증

`recommended_action`은 주된 변경 경로이고 `required_actions`는 모두 수행한다. `review-document-structure`가 포함되면 다른 action과 함께 구조도 바로잡는다.

`required_actions`, `structure_issues`, `affected_docs`, `unmapped_changes`, `renamed_paths`, `git_summary`, `soft_diff_budget_warnings`를 먼저 읽는다. 커밋 메시지만 믿지 말고 후보 source를 다시 확인한다.

사용자가 문서 구조·분할·병합 재검토를 명시하면 plan의 `no-op`보다 요청을 우선하고 `review-document-structure`를 수행한다.

모든 `update`에서 single-page primary를 읽고 서로 독립적으로 읽을 도메인·workflow가 2개 이하인지 다시 판단한다. 3개 이상이면 넓은 source 재탐색 없이 `review-document-structure`를 `required_actions`에 추가한 것으로 간주해 기존 action과 함께 수행한다.

`source_commit`은 문서가 실제로 설명하는 source 기준점이다. `reviewed_commit`은 문서 변경이 불필요하다고 판단한 commit까지 포함한 마지막 검토 기준점이다. 계획은 유효한 `reviewed_commit`을 우선 사용하고, 없으면 `source_commit`으로 fallback한다. 이후 context 문서와 marked agent 안내만 커밋된 경우 stale로 보지 않는다.

실행 분기:

- `chat`: 여기서 write 절차를 중단하고 읽기 전용으로 답한다.
- `no-op`: `required_actions`에 `no-op` 외 action이 없고 사용자 요청·single-page 의미 구조 재검토도 구조 변경을 요구하지 않은 경우에만 `sync-index`를 포함한 문서 작성과 `_plan.md` 생성을 건너뛴다. marked agent 안내가 없거나 stale할 때만 7단계를 실행하고, 8단계에서는 `record --mode update --if-changed`와 검증만 실행한다.
- 나머지 action과 강제된 `review-document-structure`: 3~8단계를 실행한다. `create-docs`만 `--mode init`, 나머지는 `--mode update`를 사용한다.

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

예상 body가 8,000자 이하이고 서로 독립적으로 읽을 도메인·workflow가 2개 이하일 때만 단일 `docs/project-context.md`를 기본으로 사용한다. 8,000자를 넘거나 독립 영역이 3개 이상이면 multi-page로 전환한다.

`review-document-structure`가 `required_actions`에 있거나 사용자 요청으로 강제되면 기존 mode를 고정값으로 보지 않고 위 기준을 다시 적용한다. 필요한 범위에서만 single/multi 전환·분할·병합하고, 기준을 이미 충족하면 구조를 유지한다.

multi-page primary는 전체 내용을 요약한 문서가 아니라 얇은 router다. body 목표는 2,500자 이하, hard limit은 4,000자다. 프로젝트 요약, 전역 변경 주의점, generated index, 문서화 백로그, 최소 근거만 두고 상세 workflow·testing·operation은 하위 문서로 옮긴다. 초기 문서는 전체 8개 이하로 유지한다. tracked primary source가 10개 이하인 작은 repo는 기본 문서와 보조 문서 1~2개까지만 쓴다.

page budget 때문에 확인된 영역을 미루면 primary 문서의 optional `## 문서화 백로그`에 `영역 — 근거: [source](../path) — 사유: 한 줄` 형식으로 남긴다. `미확정 사항`은 사실이 불명확한 내용이고, `문서화 백로그`는 확인했지만 분량 때문에 미룬 내용이다. update에서는 백로그를 먼저 읽고, 변경된 source가 항목의 근거를 건드리면 내용을 문서화한 뒤 항목을 제거한다. 식별한 중요 영역은 본문 또는 백로그 중 하나에 둔다.

multi-page일 때:

- `docs/project-context.md`를 얇은 index와 읽는 순서로 사용하고 모든 하위 문서를 미리 읽지 않음
- primary에 아래 marker를 정확히 한 쌍 두고 marker 내부는 직접 편집하지 않음

```md
<!-- project-context:index:start -->
<!-- project-context:index:end -->
```

- 각 하위 문서 상단에 아래 one-line metadata를 두고 `description`, `read_when`은 각각 160자 이하로 유지

```yaml
---
title: 결제 흐름
description: 결제·환불·웹훅 상태 흐름
read_when: 결제 API 변경 또는 환불 상태 디버깅
---
```

- `sync-index`로 metadata 기반 index를 path 순서로 생성하고 모든 하위 문서 링크·설명·읽기 조건을 primary에 반영
- 하위 문서에서 index로 돌아가는 링크
- 하위 문서가 3개 이상이면 `_plan.md`에 `source concept -> 관계 의미 -> target concept`을 기록하고 runtime, dependency, ownership, data-flow, lifecycle 관계를 설명하는 문장 안에서 peer 문서를 링크
- peer 관계가 없는 페이지는 더 넓은 문서로 합치거나 의도적인 standalone인지 재검토. 의미 없는 reciprocal link는 만들지 않음
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
- 문서화 백로그 (확인된 영역을 page budget 때문에 미룬 경우만)
- 근거
- 갱신 기록

문서 상단:

```yaml
---
generated_by: project-context
source_commit: <git canonical full object id>
updated_at: <ISO-8601 UTC>
mode: single-page
---
```

multi-page primary는 `mode: multi-page`를 쓰고 프로젝트 요약, 작업 전 확인 지점, generated `## Context Index`, optional 문서화 백로그, 근거만 유지한다.

### 6. source-grounded 작성

- 주요 주장에 실제 repo-relative Markdown source link를 붙인다.
- 구조뿐 아니라 제품·비즈니스 규칙, 존재 이유, 변경 시 판단 기준을 기록한다.
- 같은 개념은 한 canonical 섹션에 두고 다른 곳에서는 링크한다.
- multi-page primary에 하위 문서의 상세 내용을 복제하지 않는다. index 설명과 `read_when`만 보고 필요한 페이지만 선택할 수 있게 한다.
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
- unmarked `## Project Context` 섹션은 사용자 소유로 보존하고 marked 표준 섹션을 별도로 유지한다.
- nested instruction 파일은 건드리지 않는다.
- 주변 사용자 지침은 보존한다.

### 8. metadata 기록과 검증

```bash
python3 <skill-dir>/scripts/project_context_update.py sync-index .
python3 <skill-dir>/scripts/project_context_update.py delete-plan .
python3 <skill-dir>/scripts/project_context_update.py record . \
  --mode <init|update> \
  --if-changed \
  --before-hash "$PROJECT_CONTEXT_BEFORE_HASH"
python3 <skill-dir>/scripts/validate_project_context.py .
```

true `no-op`에서는 위 `sync-index`와 `delete-plan`을 생략한다.

`create-docs`는 `--mode init`, 기존 문서의 update/review/no-op은 `--mode update`를 사용한다.

metadata는 `docs/project-context/.metadata.json`에 다음 독립 필드를 기록한다.

- `generator`, `generator_version`
- `updated_at`, `run_mode`
- `source_commit`, `source_commit_short`, `reviewed_commit`
- `primary_doc`, `docs`, `doc_sources`
- `content_hash`

문서가 바뀌면 `source_commit`과 `reviewed_commit`을 현재 `HEAD`로 기록한다. committed source 변경을 검토했지만 문서 변경이 불필요하면 `source_commit`은 보존하고 `reviewed_commit`만 현재 `HEAD`로 전진시킨다. 현재 작업트리의 미커밋 변경은 commit 기준점으로 승인하지 않으므로 계속 갱신 계획에 나타날 수 있다. context 문서·metadata·marked agent 안내만 바뀐 경우에는 metadata를 갱신하지 않는다.

검증 기준:

- primary 문서와 required frontmatter 존재
- metadata 구조와 content hash 일치
- `source_commit`과 `reviewed_commit`이 Git에서 조회 가능
- mode와 실제 문서 수 일치
- multi-page 하위 문서의 `title`, `description`, `read_when` metadata 완전
- generated index가 하위 문서 metadata와 정확히 일치
- multi-page primary body 4,000자 이하. single-page body 8,000자 이하
- 모든 source link가 repo 내부 실제 경로를 가리킴
- 모든 문서에 `## 근거`와 외부 source evidence 존재
- index↔하위 문서 링크 완전
- `_plan.md` 없음
- context 문서·metadata·parent가 symlink 아님
- host absolute path와 secret-looking 값 없음
- top-level agent 안내가 하나의 current marker section

validator가 exit 0을 반환할 때까지 원인을 수정한 뒤 검증을 다시 실행한다. warning은 보고하되 완료를 막지 않는다.

## 완료 보고

다음만 보고한다.

- `docs/project-context.md` 생성·갱신·no-op 여부
- 갱신한 하위 문서
- `AGENTS.md` 또는 `CLAUDE.md` 안내 변경 여부
- 검증 결과
- stale 또는 미확정 사항

외부 서비스, provider, API key는 필요 없다.
