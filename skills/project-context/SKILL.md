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
- `init`: write gate를 충족했고 context 문서가 없다. 문서를 만들고 `finalize --mode init`으로 기록한다.
- `update`: write gate를 충족했고 context 문서가 있다. 영향 문서와 계획이 요구한 문서 구조만 고치고 `finalize --mode update --if-changed`로 기록한다.

## Helper 명령

```bash
python3 <skill-dir>/scripts/project_context_update.py snapshot .
python3 <skill-dir>/scripts/project_context_update.py plan .
python3 <skill-dir>/scripts/project_context_update.py write-plan .
python3 <skill-dir>/scripts/project_context_update.py delete-plan .
python3 <skill-dir>/scripts/project_context_update.py migrate .
python3 <skill-dir>/scripts/project_context_update.py migrate . --apply --mode update
python3 <skill-dir>/scripts/project_context_update.py sync-index .
python3 <skill-dir>/scripts/project_context_agents.py .
python3 <skill-dir>/scripts/validate_project_context.py .
python3 <skill-dir>/scripts/project_context_update.py record . --mode init|update --if-changed --before-hash <hash>
python3 <skill-dir>/scripts/project_context_update.py finalize . --mode init|update --if-changed --before-hash <hash>
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
- `migrate-wiki-schema`: read-only migration plan을 확인한 뒤 `migrate . --apply --mode update`로 schema v2 계층 구조로 이동하고 `snapshot`·`plan`을 다시 실행
- `update-affected-docs`: source link가 가리키는 변경에 연결된 문서만 갱신
- `review-unmapped-changes`: 기존 문서에 연결되지 않은 변경을 새 근거·새 섹션·무시 중 하나로 판단
- `review-generated-doc-changes`: 현재 작업트리에서 context 문서가 직접 바뀌었는지 확인
- `review-document-structure`: 현재 mode·문서 수·primary body budget을 재검토하고 필요한 분할·병합 수행
- `review-recent-history`: 이전 성공 metadata가 없어 최근 history를 기준점으로 검토
- `no-op`: 문서는 수정하지 않는다. 변경 후 되돌린 commit까지 검토 기준점에 포함되도록 `finalize --if-changed`를 실행

`recommended_action`은 주된 변경 경로이고 `required_actions`는 모두 수행한다. `review-document-structure`가 포함되면 다른 action과 함께 구조도 바로잡는다.

`required_actions`, `structure_issues`, `affected_docs`, `related_review_candidates`, `unmapped_changes`, `renamed_paths`, `git_summary`, `soft_diff_budget_warnings`를 먼저 읽는다. 커밋 메시지만 믿지 말고 후보 source를 다시 확인한다. `related_review_candidates`는 변경 page의 의미 링크 기준 incoming/outgoing 1-hop 검토 후보이며 자동 편집 대상이 아니다.

사용자가 문서 구조·분할·병합 재검토를 명시하면 plan의 `no-op`보다 요청을 우선하고 `review-document-structure`를 수행한다.

`source_commit`은 문서가 실제로 설명하는 source 기준점이다. `reviewed_commit`은 문서 변경이 불필요하다고 판단한 commit까지 포함한 마지막 검토 기준점이다. 계획은 유효한 `reviewed_commit`을 우선 사용하고, 없으면 `source_commit`으로 fallback한다. 이후 context 문서와 marked agent 안내만 커밋된 경우 stale로 보지 않는다.

실행 분기:

- `chat`: 여기서 write 절차를 중단하고 읽기 전용으로 답한다.
- `no-op`: `required_actions`에 `no-op` 외 action이 없으면 문서 작성과 `_plan.md` 생성을 건너뛴다. marked agent 안내가 없거나 stale할 때만 7단계를 실행하고, 8단계의 `finalize --mode update --if-changed`는 실행한다.
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

### 4. 위키 구조 선택

`docs/project-context.md`는 항상 홈/router다. 상세 개념이 필요하면 아래 두 단계 구조를 쓴다.

```text
docs/project-context.md
docs/project-context/<area>/index.md
docs/project-context/<area>/<concept>.md
```

- 빈 area는 만들지 않는다. home-only도 유효한 schema v2 상태다.
- 초기 생성은 최대 12개 concept page를 soft cap으로 삼고, 최소 개수는 강제하지 않는다. 이후 실제 개념이 생기면 확장한다.
- 홈 body만 4,000자 이하로 유지한다. 상세 workflow·domain·operation·testing은 concept page에 둔다.
- area 이름은 저장소의 실제 경계에 맞게 정한다. 고정 enum을 만들지 않는다.
- 홈과 모든 area index에 index marker를 정확히 한 쌍 두고 내부는 직접 편집하지 않는다.
- `sync-index`는 전체 context tree를 읽어 홈에는 area index, area index에는 concept page를 결정적으로 연결하고 바뀐 index만 쓴다.
- 기존 schema v1/평면 문서는 먼저 `migrate .` dry-run을 확인하고, write gate가 열린 `update`에서만 `migrate . --apply --mode update`를 실행한다. migration은 알 수 없는 frontmatter와 본문을 보존하고 이동된 상대 링크를 다시 계산한다.

area index frontmatter:

```yaml
---
title: 결제
description: 결제 영역의 프로젝트 컨텍스트
read_when: 결제 관련 코드를 조사하거나 변경할 때
generated_by: project-context-index
---
```

concept page frontmatter:

```yaml
---
type: workflow
title: 주문 취소 흐름
description: 취소 조건과 환불·재고 복원 과정
read_when: 주문 취소 API나 환불 상태를 변경할 때
tags: [orders, refund]
---
```

concept page는 고정 heading을 강제하지 않는다. 무엇인지, 주요 흐름과 규칙, 변경 위험, 검증 방법, 관련 개념, `## 근거`를 필요한 만큼 쓴다. 관련 page 링크는 단순 목록보다 관계 의미가 드러나는 문장에 둔다. 링크 개수는 강제하지 않는다.

### 5. 임시 계획 작성

```bash
python3 <skill-dir>/scripts/project_context_update.py write-plan .
```

`docs/project-context/_plan.md`에 작성할 문서, source evidence, 남은 질문만 둔다. 최종 완료 전 반드시 삭제한다.

`Unmapped Change Resolutions` JSON에서 각 `pending`을 처리한다.

- 문서에 source link를 추가했으면 `documented`
- 홈 `## 문서화 백로그`에 source link와 사유를 남겼으면 `backlog`와 reason
- 문서 범위 밖이면 `ignored`와 구체적 reason

`finalize`는 미해결 unmapped change가 있으면 metadata를 쓰지 않고 중단한다.

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
- 홈과 concept page에 `## 근거`와 실제 source link를 둔다. generated area index에는 요구하지 않는다.
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

### 8. 원자적 finalize와 검증

```bash
python3 <skill-dir>/scripts/project_context_update.py finalize . \
  --mode <init|update> \
  --if-changed \
  --before-hash "$PROJECT_CONTEXT_BEFORE_HASH"
python3 <skill-dir>/scripts/validate_project_context.py .
```

`finalize`는 index 동기화, unmapped resolution 확인, candidate metadata 검증, `_plan.md` 제거, metadata 원자적 교체, 최종 검증을 수행한다. 검증 실패 시 기존 metadata 기준점을 보존하고 삭제한 plan도 복구한다. true `no-op`에도 실행해 검토 기준점과 최종 상태를 확인한다.

`create-docs`는 `--mode init`, 기존 문서의 update/review/no-op은 `--mode update`를 사용한다.

metadata는 `docs/project-context/.metadata.json`에 다음 독립 필드를 기록한다.

- `generator`, `generator_version`
- `updated_at`, `run_mode`
- `source_commit`, `source_commit_short`, `reviewed_commit`
- `schema_version`, `primary_doc`, `pages`, `indexes`, `doc_sources`, `doc_hashes`
- `unmapped_resolutions`
- `content_hash`

문서가 바뀌면 `source_commit`과 `reviewed_commit`을 현재 `HEAD`로 기록한다. committed source 변경을 검토했지만 문서 변경이 불필요하면 `source_commit`은 보존하고 `reviewed_commit`만 현재 `HEAD`로 전진시킨다. 현재 작업트리의 미커밋 변경은 commit 기준점으로 승인하지 않으므로 계속 갱신 계획에 나타날 수 있다. context 문서·metadata·marked agent 안내만 바뀐 경우에는 metadata를 갱신하지 않는다.

검증 기준:

- primary 문서와 required frontmatter 존재
- metadata 구조와 content hash 일치
- `source_commit`과 `reviewed_commit`이 Git에서 조회 가능
- schema v2와 홈→area index→concept의 최대 2단계 구조 일치
- concept page의 `type`, `title`, `description`, `read_when` metadata 완전
- generated 홈/area index가 page metadata와 정확히 일치
- page별 SHA-256 hash와 현재 내용 일치
- 홈 body 4,000자 이하
- 모든 내부 link가 repo 내부 실제 경로를 가리킴
- 홈과 concept page에 `## 근거`와 source evidence 존재
- 홈→area index→concept 링크 완전
- stale index와 broken link는 error, semantic orphan은 warning
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
