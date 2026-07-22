# 갱신 절차

## 1. 저장소와 기준점 확인

repo root에서 실행한다.
helper는 `python3 -B`로 실행해 target repo 밖 skill tree에 bytecode cache를 쓰지 않는다.

```bash
git rev-parse --show-toplevel
PROJECT_CONTEXT_SOURCE_COMMIT="$(git rev-parse HEAD)"
git rev-parse --short "$PROJECT_CONTEXT_SOURCE_COMMIT"
git status --short --untracked-files=all
git log --max-count=20 --name-status --oneline "$PROJECT_CONTEXT_SOURCE_COMMIT"
```

`HEAD` tree는 마지막 커밋의 변경분만 뜻하지 않는다. 해당 시점까지 커밋된 전체 저장소 내용이다. update plan은 이전 `reviewed_commit` 이후 HEAD까지의 모든 커밋을 비교하므로 중간 커밋도 빠지지 않는다.

snapshot은 현재 worktree의 project-context 문서를 수정하기 전에 잡는다.

```bash
PROJECT_CONTEXT_BEFORE_HASH="$(python3 -B <skill-dir>/scripts/project_context_update.py snapshot .)"
python3 -B <skill-dir>/scripts/project_context_update.py plan .
```

plan의 `source_change_paths`와 영향 page는 committed 변경만 포함한다. 미커밋·untracked source는 계획에 반영하지 않고 `반영하지 않은 워크트리 소스`에 보고한다. dirty source는 중단 사유가 아니며 helper가 수정하지 않는다. 실행 중 `HEAD`가 바뀌면 새 기준점으로 snapshot과 plan부터 다시 시작한다.

## 2. 계획 해석

- `create-docs`: 홈과 필요한 concept 생성
- `migrate-wiki-schema`: migration dry-run 확인 후 apply하고 snapshot·plan 재실행
- `update-affected-docs`: source link로 연결된 page만 갱신
- `review-unmapped-changes`: 문서화, backlog, ignore 중 하나로 해소
- `review-generated-doc-changes`: 현재 context 변경 의도 확인
- `review-document-structure`: mode, depth, 홈 크기, 빈 area 수정
- `review-recent-history`: 유효한 이전 기준점이 없어 최근 history 확인
- `no-op`: 문서 본문 변경 없음

`recommended_action`은 주 경로다. `required_actions`는 모두 수행한다. `related_review_candidates`는 incoming/outgoing semantic 1-hop page다. 읽고 실제 영향이 있을 때만 수정한다.

`source_change_paths`가 비어 있어도 `HEAD`에는 이전 파일과 이력이 모두 있다. 이 필드는 전체 source inventory가 아니라 이전 검토 기준점 이후의 committed 변경 목록이다.

## 3. 기존 문서 마이그레이션

```bash
python3 -B <skill-dir>/scripts/project_context_update.py migrate .
python3 -B <skill-dir>/scripts/project_context_update.py migrate . --apply --mode update
```

기본 `migrate`는 read-only다. apply는 평면 page를 `<area>/overview.md`로 옮기고 상대 링크를 다시 계산하며, 알 수 없는 frontmatter와 본문을 보존한다. destination 충돌, 과도한 depth, symlink, 미래 schema는 거부한다. JSON의 `written_docs`는 migration 본문 write, `sync.changed_docs`는 generated index write 목록이다.

migration은 현재 worktree의 legacy project-context 문서를 입력으로 삼아 구조만 바꾸고 기존 `reviewed_commit`을 보존한다. 미커밋 source는 그대로 둔다. 이후 snapshot과 plan을 다시 실행해 아직 검토하지 않은 committed source 변경을 처리한다.

## 4. 임시 계획과 조사

문서 변경이 필요하면 실행한다.

```bash
python3 -B <skill-dir>/scripts/project_context_update.py write-plan .
```

`_plan.md`에서 예정 문서, 소스 근거, 1-hop 후보, 남은 질문을 갱신한다. `매핑되지 않은 변경 처리` JSON의 `pending`을 다음 중 하나로 바꾼다.

- `documented`: 현재 page에 source link와 설명 추가
- `backlog`: 홈 `## 문서화 백로그`에 source link·사유 추가하고 JSON reason 작성
- `ignored`: 문서 범위 밖인 이유를 JSON reason에 작성

source link를 추가한 documented 항목은 finalize가 자동 확인한다. pending, 근거 없는 backlog, 이유 없는 ignore는 실패한다.

source 조사에는 고정한 Git tree를 사용한다.

```bash
git ls-tree -r --name-only "$PROJECT_CONTEXT_SOURCE_COMMIT"
git show "$PROJECT_CONTEXT_SOURCE_COMMIT":<path>
git grep -n -e <pattern> "$PROJECT_CONTEXT_SOURCE_COMMIT" -- <paths>
git log "$PROJECT_CONTEXT_SOURCE_COMMIT" -- <paths>
git blame "$PROJECT_CONTEXT_SOURCE_COMMIT" -- <path>
```

직접 파일 read나 CodeGraph가 current worktree를 읽는 경우 dirty source가 섞일 수 있다. 해당 결과는 고정한 commit의 `git show`·`git grep`으로 확인하기 전까지 문서 근거로 쓰지 않는다.

## 5. 문서 작성

affected page와 필요한 1-hop 후보 source만 조사한다. rename은 old/new path를 함께 확인한다. 홈의 `source_commit`만 `PROJECT_CONTEXT_SOURCE_COMMIT`과 맞춘다. concept에는 page별 `source_commit`을 넣지 않는다. source link는 고정한 Git tree에 실제로 존재해야 한다. index marker는 건드리지 않는다.

현재 worktree의 `docs/project-context*`는 dirty 여부와 무관하게 관리 대상으로 갱신한다. 정확한 기존 문장과 사용자 초안은 보존하고, committed source와 충돌하는 내용은 수정한다. generated 홈·area index와 metadata는 helper 결과로 교체한다. 미커밋 source 내용은 문서에 반영하지 않으며 원본도 변경하지 않는다.

## 6. 에이전트 안내

```bash
python3 -B <skill-dir>/scripts/project_context_agents.py .
```

기존 top-level `AGENTS.md`, `CLAUDE.md`만 갱신한다. 둘 다 없으면 `AGENTS.md`를 만든다. marked 섹션만 관리하고 unmarked 지침과 nested 파일은 보존한다.

## 7. 최종 확정

```bash
test "$(git rev-parse HEAD)" = "$PROJECT_CONTEXT_SOURCE_COMMIT"
python3 -B <skill-dir>/scripts/project_context_update.py finalize . \
  --mode <init|update> \
  --if-changed \
  --before-hash "$PROJECT_CONTEXT_BEFORE_HASH"
python3 -B <skill-dir>/scripts/validate_project_context.py .
```

finalize 순서:

1. managed path·Git ignore·symlink 경계 확인
2. 전체 context tree에서 index preflight 후 동기화
3. committed plan과 unmapped resolution 확인
4. page/source/hash metadata candidate 생성
5. source link가 현재 `HEAD` tree에 존재하는지 포함해 candidate 전체 검증
6. `_plan.md` 안전 삭제
7. metadata 원자 교체
8. on-disk 최종 검증

candidate 또는 최종 검증이 실패하면 기존 metadata 기준점을 보존한다. metadata 교체 뒤 실패하면 metadata와 plan을 복구한다.

true no-op은 `_plan.md`를 만들지 않는다. 그래도 agent 안내 확인과 finalize를 실행해 committed source 검토 기준점이 필요한 경우에만 전진시킨다. `반영하지 않은 워크트리 소스`는 그대로 남아 있어도 이 기준점에 포함되지 않는다.
