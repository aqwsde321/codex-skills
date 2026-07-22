# Update workflow

## 1. 저장소와 기준점 확인

repo root에서 실행한다.
helper는 `python3 -B`로 실행해 target repo 밖 skill tree에 bytecode cache를 쓰지 않는다.

```bash
git rev-parse --show-toplevel
git rev-parse --short HEAD
git status --short --untracked-files=all
git log --max-count=20 --name-status --oneline
```

snapshot은 문서 수정 전에 잡는다.

```bash
PROJECT_CONTEXT_BEFORE_HASH="$(python3 -B <skill-dir>/scripts/project_context_update.py snapshot .)"
python3 -B <skill-dir>/scripts/project_context_update.py plan .
```

## 2. Plan 해석

- `create-docs`: 홈과 필요한 concept 생성
- `migrate-wiki-schema`: migration dry-run 확인 후 apply하고 snapshot·plan 재실행
- `update-affected-docs`: source link로 연결된 page만 갱신
- `review-unmapped-changes`: 문서화, backlog, ignore 중 하나로 해소
- `review-generated-doc-changes`: 현재 context 변경 의도 확인
- `review-document-structure`: mode, depth, 홈 크기, 빈 area 수정
- `review-recent-history`: 유효한 이전 기준점이 없어 최근 history 확인
- `no-op`: 문서 본문 변경 없음

`recommended_action`은 주 경로다. `required_actions`는 모두 수행한다. `related_review_candidates`는 incoming/outgoing semantic 1-hop page다. 읽고 실제 영향이 있을 때만 수정한다.

## 3. Legacy migration

```bash
python3 -B <skill-dir>/scripts/project_context_update.py migrate .
python3 -B <skill-dir>/scripts/project_context_update.py migrate . --apply --mode update
```

기본 `migrate`는 read-only다. apply는 평면 page를 `<area>/overview.md`로 옮기고 상대 링크를 다시 계산하며, 알 수 없는 frontmatter와 본문을 보존한다. destination 충돌, 과도한 depth, symlink, 미래 schema는 거부한다. JSON의 `written_docs`는 migration 본문 write, `sync.changed_docs`는 generated index write 목록이다.

migration은 구조 변경만 기록하고 기존 `reviewed_commit`을 보존한다. 이후 snapshot과 plan을 다시 실행해 아직 검토하지 않은 source 변경을 처리한다.

## 4. 임시 계획과 조사

문서 변경이 필요하면 실행한다.

```bash
python3 -B <skill-dir>/scripts/project_context_update.py write-plan .
```

`_plan.md`에서 intended page, source evidence, 1-hop 후보, 남은 질문을 갱신한다. `Unmapped Change Resolutions` JSON의 `pending`을 다음 중 하나로 바꾼다.

- `documented`: 현재 page에 source link와 설명 추가
- `backlog`: 홈 `## 문서화 백로그`에 source link·사유 추가하고 JSON reason 작성
- `ignored`: 문서 범위 밖인 이유를 JSON reason에 작성

source link를 추가한 documented 항목은 finalize가 자동 확인한다. pending, 근거 없는 backlog, 이유 없는 ignore는 실패한다.

## 5. 문서 작성

affected page와 필요한 1-hop 후보 source만 조사한다. rename은 old/new path를 함께 확인한다. 홈·concept의 `source_commit`은 실제 설명 기준점과 맞춘다. index marker는 건드리지 않는다.

## 6. Agent 안내

```bash
python3 -B <skill-dir>/scripts/project_context_agents.py .
```

기존 top-level `AGENTS.md`, `CLAUDE.md`만 갱신한다. 둘 다 없으면 `AGENTS.md`를 만든다. marked 섹션만 관리하고 unmarked 지침과 nested 파일은 보존한다.

## 7. Finalize

```bash
python3 -B <skill-dir>/scripts/project_context_update.py finalize . \
  --mode <init|update> \
  --if-changed \
  --before-hash "$PROJECT_CONTEXT_BEFORE_HASH"
python3 -B <skill-dir>/scripts/validate_project_context.py .
```

finalize 순서:

1. 전체 tree에서 index 동기화
2. 현재 plan과 unmapped resolution 확인
3. page/source/hash metadata candidate 생성
4. candidate로 전체 검증
5. `_plan.md` 안전 삭제
6. metadata 원자 교체
7. on-disk 최종 검증

candidate 또는 최종 검증이 실패하면 기존 metadata 기준점을 보존한다. metadata 교체 뒤 실패하면 metadata와 plan을 복구한다.

true no-op은 `_plan.md`를 만들지 않는다. 그래도 agent 안내 확인과 finalize를 실행해 committed source 검토 기준점이 필요한 경우에만 전진시킨다.
