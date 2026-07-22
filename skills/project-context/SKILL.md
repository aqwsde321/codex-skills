---
name: project-context
description: Read existing or explicitly create, refresh, and validate source-grounded project context documentation for a code repository. Use when the user asks for repository project context, "프로젝트 컨텍스트 세팅", "프로젝트 컨텍스트 wiki 생성", "프로젝트 컨텍스트 문서 갱신", or invokes "$project-context". Do not trigger for ordinary implementation, debugging, or review merely because onboarding docs are missing.
---

# Project Context

## 목적

저장소의 구조, 주요 흐름, 변경 위험, 검증 방법을 source-grounded 장기 위키로 유지한다. 진입점은 `docs/project-context.md`다. 현재 source가 문서보다 우선한다.

이 스킬은 외부 문서화 서비스나 코드 인덱서를 설치·설정·호출하지 않는다. 저장소 지침에 지정된 코드 탐색 도구만 사용한다.

## 권한과 안전 경계

사용자가 프로젝트 컨텍스트 생성·세팅·갱신을 명시했거나, 더 좁은 read-only 요청 없이 `$project-context`를 직접 호출한 경우에만 write한다. 문서 부재·stale 또는 일반 구현·디버깅·리뷰 요청은 write 권한이 아니다.

허용 write:

- `docs/project-context.md`
- `docs/project-context/`
- top-level `AGENTS.md` 또는 `CLAUDE.md`의 project-context marker 섹션

금지:

- source code 수정
- target repo 밖 검색·쓰기
- `.env`, private key, token, credential 파일 읽기
- symlink를 통한 managed path 우회
- 사용자 소유 문서나 unmarked agent 지침 덮어쓰기

`.env.example`은 placeholder만 있을 때만 읽는다. 절대경로, private URL, secret을 생성 문서나 metadata에 기록하지 않는다.

## 모드

- `chat`: write gate가 열리지 않았다. 문서와 metadata를 수정하지 않는다. 홈을 먼저 읽고 작업과 `read_when`이 맞는 area/concept만 연다. 정확한 최신 동작이 필요하거나 문서가 stale·모호·source와 충돌할 때만 관련 source를 좁게 확인한다.
- `init`: write gate가 열렸고 홈 문서가 없다. 위키를 생성하고 `finalize --mode init`으로 기록한다.
- `update`: write gate가 열렸고 홈 문서가 있다. 영향 page와 필요한 1-hop 후보만 검토하고 `finalize --mode update --if-changed`로 기록한다.

## Reference routing

`chat`에서 구조 해석이 필요하면 [wiki-model.md](references/wiki-model.md)만 읽는다.

`init` 또는 `update`에서는 작업 전에 아래 파일을 순서대로 전부 읽는다.

1. [wiki-model.md](references/wiki-model.md)
2. [authoring.md](references/authoring.md)
3. [update-workflow.md](references/update-workflow.md)
4. [validation.md](references/validation.md)

## 불변 규칙

- 위키 탐색 깊이는 `홈 → area index → concept` 최대 2단계다.
- 빈 area를 만들지 않는다. home-only schema v2도 유효하다.
- 모든 concept는 `type`, `title`, `description`, `read_when` frontmatter와 `## 근거` source link를 가진다.
- area index는 helper가 관리한다. generated marker 내부를 직접 편집하지 않는다.
- 관련 concept는 관계 의미가 드러나는 문장으로 연결한다. 링크 개수는 강제하지 않는다.
- `source_commit`은 문서가 설명하는 source 기준점, `reviewed_commit`은 변경 불필요까지 확인한 기준점이다.
- source와 연결되지 않은 변경은 문서화, 홈 backlog, 이유 있는 ignore 중 하나로 해소한다.
- page hash, source map, index는 현재 파일과 일치해야 한다.
- warning은 보고 대상이다. error 또는 non-zero exit는 완료 실패다.

## 실행 골격

repo root를 먼저 확인한다.

```bash
git rev-parse --show-toplevel
git rev-parse --short HEAD
git status --short --untracked-files=all
```

write run은 snapshot과 plan으로 시작한다.
모든 helper는 `-B`로 실행해 설치된 skill tree에 bytecode cache를 남기지 않는다.

```bash
PROJECT_CONTEXT_BEFORE_HASH="$(python3 -B <skill-dir>/scripts/project_context_update.py snapshot .)"
python3 -B <skill-dir>/scripts/project_context_update.py plan .
```

legacy schema나 평면 page가 있으면 migration dry-run을 먼저 확인한다.

```bash
python3 -B <skill-dir>/scripts/project_context_update.py migrate .
python3 -B <skill-dir>/scripts/project_context_update.py migrate . --apply --mode update
```

migration 후 snapshot과 plan을 다시 실행한다. migration은 구조만 옮기며 아직 검토하지 않은 source commit을 승인하지 않는다.

문서 변경이 필요한 run은 임시 계획을 만든다.

```bash
python3 -B <skill-dir>/scripts/project_context_update.py write-plan .
```

문서 작성 뒤 agent 안내를 보장하고 finalize한다.

```bash
python3 -B <skill-dir>/scripts/project_context_agents.py .
python3 -B <skill-dir>/scripts/project_context_update.py finalize . \
  --mode <init|update> \
  --if-changed \
  --before-hash "$PROJECT_CONTEXT_BEFORE_HASH"
python3 -B <skill-dir>/scripts/validate_project_context.py .
```

true `no-op`은 문서와 `_plan.md`를 만들지 않지만 agent 안내 확인과 `finalize --mode update --if-changed`는 실행한다.

## Helper 계약

- `plan`: source 변경→영향 page, 변경 page→semantic 1-hop 후보, unmapped 변경, 구조 오류를 출력
- `write-plan`: managed `_plan.md` 생성
- `migrate`: 기본 read-only; `--apply`일 때만 schema v2로 이동
- `sync-index`: 전체 tree를 읽고 누락 area index와 stale marker만 갱신
- `finalize`: plan resolution 확인, candidate metadata 검증, plan 삭제, metadata 원자 교체, 최종 검증
- `record`: 저수준 호환 명령. 정상 스킬 run은 `finalize` 사용
- `validate_project_context.py`: 현재 on-disk 최종 상태 검증

helper의 managed path override는 허용하지 않는다. 실패를 우회해 metadata를 수동으로 전진시키지 않는다.

## 완료 조건

- 필요한 page만 source 근거에 맞게 생성·갱신됨
- generated 홈/area index가 current
- unmapped change가 모두 해소됨
- `_plan.md`가 없음
- metadata schema, Git 기준점, source map, page hash, 전체 content hash가 current
- top-level agent marker가 current
- 최종 validator exit 0

## 완료 보고

다음만 간결히 보고한다.

- 홈과 갱신한 concept page
- 생성·갱신한 area index
- agent 안내 변경 여부
- unmapped 처리 요약
- 검증 결과와 warning
