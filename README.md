# Codex Skills

개인 또는 팀에서 재사용할 수 있는 Codex skill 모음이다. 사용자용 번호 호출어 6개와 내부 workflow/helper skill을 포함한다.

## Primary Shortcuts

평소에는 아래 6개만 기억하면 된다. 번호는 작업 단계 순서이며, 기존 비번호 호출어도 별칭으로 계속 쓸 수 있다.

| 호출어 | 내부 동작 | 언제 쓰나 |
| --- | --- | --- |
| `00큰그림` | `$zoom-out` | 코드 구조, 호출 흐름, 책임 경계를 먼저 파악할 때 |
| `10설계` | `$plan-grill`, `$feature-flow-review`, `$api-design-review` 중 선택 | 구현 전 계획, 기능 플로우, API 설계를 검토할 때 |
| `20진단` | `$diagnose` | 버그, 실패, 예외, 성능 회귀를 재현부터 볼 때 |
| `30구현` | `$tdd` | 도메인 규칙을 확인하고 신규 구현이나 원인이 확인된 수정 구현을 테스트 우선으로 진행할 때 |
| `40리뷰` | `$review-fix-test` | 작업 후 변경분이나 커밋을 리뷰, 수정, 검증할 때. 과설계만 보려면 `과설계리뷰` |
| `50기록` | `$solution-capture` | 사용자가 확인한 재사용 가능한 해결 지식을 기록할 때 |

일반 기능 흐름은 `00큰그림` -> `10설계` -> `30구현` -> `40리뷰` -> `50기록`이다.
버그/장애 흐름은 `20진단` -> `30구현` -> `40리뷰` -> `50기록`이다.

`10설계`는 단계에 따라 나뉜다. 코드 구조를 모르면 먼저 `zoom-out`으로 큰그림을 잡고, 계획이 모호하면 `plan-grill`, 기능 흐름이 핵심이면 `feature-flow-review`, 플로우가 확정되어 API 초안이 필요하면 `api-design-review`를 사용한다.

기본 구현 흐름은 `10설계` 후 `30구현`이다. `30구현`은 첫 테스트 전에 도메인 용어, 핵심 규칙, invariant, 규칙 소유 위치를 가볍게 확인한다. 버그 원인이 아직 확인되지 않았으면 `30구현`보다 `20진단`을 먼저 사용한다.

## Internal Skills

| Skill | 호출어 | 용도 |
| --- | --- | --- |
| `plan-grill` | `10설계`, `설계리뷰`, `계획압박`, `그릴`, `grill`, `허점 찾아줘`, `질문으로 털어줘` | 구현 전에 계획을 한 질문씩 압박해 모호한 분기, 위험한 가정, 빠진 결정을 줄인다. |
| `feature-flow-review` | `기능플로우리뷰`, `플로우리뷰`, `기능 흐름 정리`, `플로우 문서 작성` | API 상세 설계 전에 신규 기능의 플로우, 분기, 상태 전이, 토큰/외부 연동을 정리한다. |
| `api-design-review` | `API리뷰`, `기획서리뷰`(확정 플로우), `엔드포인트리뷰`, `API 설계 리뷰`, `API 초안 작성` | 프로젝트별 컨벤션, 기존 코드 패턴, 또는 Spring/REST 기본 관례를 기준으로 API 엔드포인트 초안과 설계 엣지케이스를 정리한다. |
| `diagnose` | `20진단`, `진단`, `디버깅`, `버그진단`, `원인분석`, `재현부터` | 버그/성능 문제를 추측으로 고치지 않고 재현 루프, 가설, 계측, 회귀 테스트 순서로 진단한다. |
| `tdd` | `30구현`, `TDD`, `테스트우선`, `테스트 먼저`, `red-green-refactor` | 도메인 규칙과 invariant를 확인한 뒤 공개 인터페이스를 통한 행동 테스트를 먼저 쓰고 작은 수직 슬라이스로 구현한다. |
| `zoom-out` | `00큰그림`, `큰그림`, `전체맥락`, `상위맥락`, `구조파악` | 낯선 코드 영역의 모듈, 호출자, 책임 경계, 데이터 흐름을 구현 전에 정리한다. |
| `project-context` | `$project-context`, `프로젝트 컨텍스트 세팅`, `Codex 문서화`, `OpenWiki 대체`, `wiki 생성` | `codebase-memory-mcp`와 Codex-native source-grounded `docs/project-context.md`로 repo 온보딩 문서를 생성/갱신한다. |
| `review-fix-test` | `40리뷰`, `변경리뷰`, `커밋리뷰`, `동시리뷰`, `반복리뷰`, `반복변경리뷰`, `반복커밋리뷰`, `과설계리뷰`, `단순화리뷰`, `삭제리뷰` | 현재 변경분, 마지막 커밋, 또는 둘 다를 Core Risk, Standards, Spec, Simplicity 축으로 리뷰/수정/검증한다. |
| `simplification-debt` | `단순화부채`, `부채리뷰`, `단순화 부채`, `ponytail-debt` | `ponytail:` 주석을 모아 의도적 단순화의 한계와 재검토 트리거를 점검한다. |
| `solution-capture` | `50기록`, `해결기록`, `해결지식`, `지식축적`, `컴파운드`, `문제 해결 기록` | 해결한 문제, 디버깅 결과, 도구 세팅, 프로젝트 고유 패턴을 `docs/solutions/`에 재사용 가능한 지식으로 기록한다. |

## Repository Layout

```text
codex-skills/
├── AGENTS.md
├── README.md
├── docs/
│   └── solutions/
│       └── README.md
├── instructions/
│   ├── docs.md
│   ├── git.md
│   └── skill-shortcuts.md
└── skills/
    ├── api-design-review/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    ├── diagnose/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    ├── feature-flow-review/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    ├── plan-grill/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    ├── project-context/
    │   ├── SKILL.md
    │   ├── agents/
    │   │   └── openai.yaml
    │   └── scripts/
    │       ├── project_context_agents.py
    │       ├── project_context_update.py
    │       └── validate_project_context.py
    ├── review-fix-test/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    ├── simplification-debt/
    │   ├── SKILL.md
    │   ├── agents/
    │   │   └── openai.yaml
    │   └── scripts/
    │       └── collect_simplification_debt.py
    ├── solution-capture/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    ├── tdd/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    └── zoom-out/
        ├── SKILL.md
        └── agents/
            └── openai.yaml
```

## Installation

### Manual Install

```bash
mkdir -p ~/.codex/skills ~/.codex/instructions
cp -R skills/* ~/.codex/skills/
cp instructions/git.md ~/.codex/instructions/
cp instructions/skill-shortcuts.md ~/.codex/instructions/
```

설치 후 Codex를 재시작하면 skill 목록에 반영된다.

`solution-capture`를 프로젝트에서 쓰려면 해당 프로젝트에 `docs/solutions/`를 두고, 가능하면 이 저장소의 `docs/solutions/README.md` 내용을 복사하거나 프로젝트 `AGENTS.md`에 Documented Solutions 규칙을 추가한다.

### Global Instructions

짧은 한국어 호출어와 Git 규칙을 전역에서 쓰려면 `~/.codex/AGENTS.md` 또는 프로젝트 `AGENTS.md`에서 instruction 파일을 참조한다.

```md
## Additional Instructions

- Git/커밋 메시지 규칙은 `~/.codex/instructions/git.md`를 따른다.
- 스킬 호출어와 실행 보조 규칙은 `~/.codex/instructions/skill-shortcuts.md`를 따른다.
```

## Usage

대표 번호 호출어:

```text
00큰그림
10설계
20진단
30구현
40리뷰
50기록
```

기존 호출어와 세부 호출어도 직접 사용할 수 있다.

```text
큰그림
설계리뷰
TDD
진단
변경리뷰
과설계리뷰
계획압박
기능플로우리뷰
API리뷰
커밋리뷰
해결기록
단순화부채
```

`40리뷰`와 `변경리뷰`는 현재 변경분을 기본 대상으로 한다. 마지막 커밋을 보려면 `커밋리뷰`, 커밋과 현재 변경분을 함께 보려면 `동시리뷰`, 수정할 게 없을 때까지 반복하려면 `반복리뷰`를 직접 쓸 수 있다. `커밋리뷰`는 후속 수정이 생기면 기본적으로 수정 커밋까지 만든다. 요구사항 문서가 있으면 `40리뷰 spec=docs/features/example.md`처럼 넘길 수 있다.

`단순화부채`는 `ponytail:` 주석을 스캔해 의도적으로 단순하게 둔 구현의 한계와 재검토 트리거를 보고한다. 기본은 읽기 전용 보고이며, 사용자가 요청하면 ledger를 Markdown 파일로 저장한다.

`plan-grill`, `feature-flow-review`, `api-design-review`, `diagnose`, `tdd`, `review-fix-test`가 재사용 가능한 학습을 만든 경우에는 완료 보고에서 `$solution-capture`를 제안한다. 사용자가 확인하기 전에는 자동으로 기록하지 않는다.

## Skill Format

각 skill은 `skills/<skill-name>/SKILL.md` 형태의 독립 폴더다. UI 메타데이터가 필요한 경우 `agents/openai.yaml`을 함께 둔다. skill 내부에는 별도 README나 changelog를 두지 않고, 공유/설치 안내는 repo root 문서에서 관리한다.

`instructions/`는 `AGENTS.md`가 참조하는 보조 지침이다. Codex의 명령 승인 정책용 `rules/`와 의미가 겹치지 않도록 일반 Markdown 지침은 이 폴더에 둔다.

`docs/solutions/`는 해결한 문제와 재사용 가능한 작업 패턴을 기록하는 지식 저장소다. 반복될 수 있는 버그, 디버깅 결과, 프로젝트 관례를 문서화할 때 사용한다.

`plan-grill`, `diagnose`, `tdd`, `zoom-out`은 `mattpocock/skills`의 경량 엔지니어링 워크플로를 이 저장소 스타일에 맞게 선별 적용한 스킬이다. 전체 외부 플러그인을 설치하지 않고 필요한 절차만 유지한다.

## Development

- skill을 수정할 때는 `SKILL.md` frontmatter의 `name`과 `description`을 먼저 확인한다.
- 새 skill은 category 하위 폴더를 만들지 말고 `skills/<skill-name>/` 아래에 둔다.
- `review-fix-test`는 review workflow의 단일 엔진이다. 새 리뷰 호출어를 추가할 때는 skill을 늘리기보다 option parsing과 `instructions/skill-shortcuts.md` 매핑을 확장한다.
- 단축어나 커밋 규칙을 수정할 때는 `instructions/` 아래 파일을 먼저 수정한다.
- 공유 전 YAML frontmatter와 `agents/openai.yaml` 구문을 검증한다.
