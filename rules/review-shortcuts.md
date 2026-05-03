# Review Shortcuts

## Code Review Defaults

- 버그, 회귀, 엣지케이스, 테스트 정합성을 최우선으로 확인한다.
- 보안, 데이터 손상, 동시성, 성능 회귀처럼 실제 운영 리스크가 있으면 함께 지적한다.
- 스타일/취향 코멘트는 실제 유지보수 리스크가 있을 때만 언급한다.
- 발견 사항은 심각도순으로 파일/라인 근거와 함께 제시한다.
- 문제가 없으면 중요 이슈 없음과 남은 테스트 리스크만 간단히 말한다.

## Shortcut Mapping

- 사용자가 `변경리뷰`, `작업트리 리뷰`, `워킹트리 리뷰`, `현재 변경 리뷰`처럼 요청하면 `$review-fix-test` skill을 사용한다. 기본값은 `target=changes max=1 commit=false verify_max=3`이다.
- 사용자가 `커밋리뷰`, `리뷰커밋`, `막커밋 리뷰`, `마지막 커밋 리뷰하고 수정`처럼 요청하면 `$review-fix-test target=commit`으로 해석한다. `target=commit`의 기본값은 `commit=true`이다.
- 사용자가 `동시리뷰`, `커밋이랑 변경 같이 리뷰`, `마지막 커밋과 현재 변경 리뷰`처럼 요청하면 `$review-fix-test target=both`로 해석한다. `target=both`의 기본값은 `commit=false`이다.
- 사용자가 `반복변경리뷰`, `반복리뷰`, `끝까지 리뷰`, `수정할 거 없을 때까지 리뷰`처럼 요청하면 `$review-fix-test max=10`으로 해석한다.
- 사용자가 `반복커밋리뷰`처럼 요청하면 `$review-fix-test target=commit max=10`으로 해석한다.
- 사용자가 숫자만 함께 주면 `max`로 해석한다. 예: `변경리뷰 5`, `커밋리뷰 5`, `동시리뷰 3`.
- 사용자가 `max=5`, `최대 5번`, `5회까지만`처럼 명시하면 그 값을 review cycle 최대 반복 수로 사용한다.
- 사용자가 `verify_max=5`처럼 명시하면 한 cycle 안에서 검증 실패를 고치는 내부 반복 수로 사용한다. 기본값은 3이다.
- `$review-fix-test commit 5`, `$review-fix-test 변경 5`, `$review-fix-test both max=3` 같은 shorthand를 허용한다.

## Execution Policy

- 새 에이전트는 리뷰만 맡기고, 메인 에이전트가 findings를 판단해 필요한 부분만 수정한다.
- 검증 실패 시 메인 에이전트가 수정과 검증을 `verify_max`까지 반복한다.
- 검증이 통과하면 새 에이전트로 post-fix 리뷰를 수행한다.
- post-fix 리뷰에서 actionable finding이 남으면 다음 review cycle로 넘어가며, `max`에 도달하면 중단하고 남은 리스크를 보고한다.
- `리뷰만`이라고 하면 수정/검증/커밋하지 않는다.
