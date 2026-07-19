# Skill Shortcuts

번호 호출어는 사용하지 않는다. 이 파일은 자연어 별칭과 라우팅만 정의하며, 실행 절차는 각 `SKILL.md`를 따른다. Explicit-only skill은 자연어 별칭만으로 주입이 보장되지 않으므로 `$skill-name`으로 호출한다.

| 자연어 호출어 | Skill |
| --- | --- |
| `설계리뷰` | `$grill-me` |
| `진단` | `$diagnosing-bugs` |
| `TDD` | `$tdd` |
| `코드리뷰` | `$code-review` |
| `기능플로우리뷰` | `$feature-flow-review` |
| `API리뷰` | `$api-design-review` |
| `해결기록` | `$solution-capture` |
| `스킬검증` | `$skill-quality-review` |

## Routing

- `설계리뷰`는 결정이 남은 계획을 질문으로 검증할 때 사용한다. 기능 흐름이나 API 설계를 명시하면 각각 전용 skill을 사용한다.
- `$grill-me`, `$solution-capture`, `$skill-quality-review`는 explicit-only다. 자연어 별칭만 쓰지 말고 `$` 호출을 사용한다.
- `$skill-quality-review`는 대상이 없으면 현재 세션의 활성 skill 전체, skill 하나를 주면 개별 심층검사, 디렉터리를 주면 해당 suite를 감사한다.
- `진단`은 `$diagnosing-bugs`를 사용하되 `AGENTS.md`의 Bug Fix/JPA 원칙을 우선한다.
- `코드리뷰`는 fixed point부터 `HEAD`와 현재 작업트리까지 Standards와 Spec을 보고한다. fixed point가 없으면 묻는다.
- finding 수정, 테스트, 커밋은 `$code-review` 옵션이 아니다. 필요하면 일반 요청으로 별도 수행한다.
