# 작성 지침

## 소스 조사

먼저 저장소 지침에 정의된 코드 탐색 도구를 사용한다. 후보가 좁혀지면 필요한 파일만 직접 읽는다.

우선 후보:

- `AGENTS.md`, `CLAUDE.md`, `README.md`
- package/build manifest와 lockfile
- app entrypoint, route/controller, schema/migration
- tests/evals, CI, Docker, operational script
- 기존 docs, runbook, ADR
- plan의 affected, 1-hop candidate, unmapped 파일

init에서는 최근 `git log`, 선별적 `git show`와 `git blame`으로 핵심 workflow의 이유를 확인한다. 커밋 메시지만 근거로 쓰지 않는다. 기존 문서와 source가 충돌하면 현재 source를 우선하고 확인되지 않은 내용은 `확인 필요`로 표시한다.

큰 repo에서 병렬 read-only 조사가 유용하면 좁은 area 단위로 나눈다. 최종 문장과 source 근거는 메인 agent가 직접 검증한다.

## 작성 원칙

- 파일 inventory보다 시스템이 왜 그렇게 작동하는지 설명한다.
- 제품·비즈니스 규칙, 상태 전이, 소유권, 변경 위험, 검증 방법을 기록한다.
- 주요 주장 가까이에 repo-relative Markdown source link를 둔다.
- 같은 개념은 한 canonical page에 쓰고 다른 page에서는 관계 문장으로 링크한다.
- 홈에 concept 상세를 복제하지 않는다.
- 기존의 정확한 문장은 보존하고 stale한 주장만 고친다.
- formatting-only, wording polish, table reorder를 update 이유로 삼지 않는다.
- source 변경이 작으면 보통 영향 page도 작게 유지한다.
- page가 얇아도 독립 개념이면 유지할 수 있다. 근거·판단 가치가 없을 때만 합친다.
- 의미 없는 reciprocal link나 링크 수 채우기용 문장을 만들지 않는다. 링크만 있거나 `label: [A], [B]` 형태인 navigation 목록은 semantic 관계로 인정되지 않는다. `Depends on: [A]`, `Calls: [B]`처럼 관계 동작을 명시한 canonical label은 예외다.
- navigation 링크 사이에 접속사와 구분자만 있어도 semantic 관계로 인정되지 않는다.
- canonical relation label을 `**...**` 또는 `__...__`로 강조해도 semantic 판정은 같다.

## 개념 문서 내용

필요에 따라 다음을 담는다.

- 무엇이며 왜 존재하는가
- 주요 actor, 상태, 데이터 흐름
- 정상·실패·보상 흐름
- 변경 시 함께 확인할 경계
- 실행·테스트·운영 검증
- 관련 concept와 관계 의미
- 미확정 사항
- `## 근거`

개념 page의 heading은 내용에 맞게 정한다. 홈은 validator와 작성 계약이 어긋나지 않도록 canonical H2를 쓴다.

- 모든 홈: `## 프로젝트 요약`, `## 변경 판단`
- single-page 홈 추가: `## 검증 방법`, `## 주요 흐름`

읽는 사람이 변경 판단을 내리는 데 필요한 정보만 쓴다.

## 문서화 백로그

source 변화가 중요하지만 이번 run에서 concept로 확정하기 이르면 홈의 optional `## 문서화 백로그`에 남긴다.

```md
- 정산 재처리 — 근거: [worker](../src/settlement/worker.ts) — 사유: 운영 재시도 정책 확인 필요
```

backlog는 source link와 구체적 사유가 필요하다. 단순히 page budget을 채우기 위한 대기열로 쓰지 않는다. 이후 해당 source가 바뀌면 내용을 문서화하거나 backlog 사유를 다시 확인한다.

## 금지 내용

- host absolute path
- secret, credential, 실제 private endpoint
- 긴 commit hash history나 전체 파일 목록
- source로 확인할 수 없는 추측
- generated index marker 수동 편집
- source map만 있는 빈 concept page
