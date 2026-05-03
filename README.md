# Codex Skills

개인 또는 팀에서 재사용할 수 있는 Codex skill 모음이다. 현재는 기능 플로우 리뷰, API 설계 리뷰, git 변경분 리뷰 workflow skill을 포함한다.

## Skills

| Skill | 호출어 | 용도 |
| --- | --- | --- |
| `feature-flow-review` | `기능플로우리뷰`, `플로우리뷰`, `기능 흐름 정리`, `플로우 문서 작성` | API 상세 설계 전에 신규 기능의 플로우, 분기, 상태 전이, 토큰/외부 연동을 정리한다. |
| `api-design-review` | `API리뷰`, `기획서리뷰`(확정 플로우), `엔드포인트리뷰`, `API 설계 리뷰`, `API 초안 작성` | 프로젝트별 컨벤션, 기존 코드 패턴, 또는 Spring/REST 기본 관례를 기준으로 API 엔드포인트 초안과 설계 엣지케이스를 정리한다. |
| `review-fix-test` | `변경리뷰`, `커밋리뷰`, `동시리뷰`, `반복리뷰`, `반복변경리뷰`, `반복커밋리뷰` | 현재 변경분, 마지막 커밋, 또는 둘 다를 리뷰/수정/검증한다. |

## Repository Layout

```text
codex-skills/
├── AGENTS.md
├── README.md
├── instructions/
│   ├── git.md
│   └── skill-shortcuts.md
└── skills/
    ├── api-design-review/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    ├── feature-flow-review/
    │   ├── SKILL.md
    │   └── agents/
    │       └── openai.yaml
    └── review-fix-test/
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

### Global Instructions

짧은 한국어 호출어와 Git 규칙을 전역에서 쓰려면 `~/.codex/AGENTS.md` 또는 프로젝트 `AGENTS.md`에서 instruction 파일을 참조한다.

```md
## Additional Instructions

- Git/커밋 메시지 규칙은 `~/.codex/instructions/git.md`를 따른다.
- 스킬 호출어와 실행 보조 규칙은 `~/.codex/instructions/skill-shortcuts.md`를 따른다.
```

## Usage

신규 기능이나 큰 기능 변경을 API 상세 설계 전에 플로우, 분기, 상태 전이, 토큰/임시 저장 중심으로 정리한다. 항상 API 상세 설계로 넘어가기 전에 멈춘다.

```text
기능플로우리뷰
플로우리뷰
기능 흐름 정리
기능플로우리뷰 문서까지
플로우 문서 작성 경로: docs/features/customer_account_link_flow.md
```

확정된 플로우나 API 관점으로 정리할 기획서를 바탕으로 전체 엔드포인트 초안, Request/Response 필드, 처리 내용, 설계 엣지케이스를 정리한다. 프로젝트별 참고문서와 기존 코드 패턴을 우선 적용하고, 둘 다 없으면 Spring/REST 기본 관례를 가정으로 표시한다.

`기획서리뷰`만 요청했고 다단계 흐름, 상태 전이, 토큰, 외부 연동이 미확정이면 `기능플로우리뷰`를 먼저 사용한다.

```text
API리뷰
기획서리뷰
엔드포인트리뷰
API리뷰 입력 문서: docs/features/customer_account_link_flow.md
API리뷰 참고문서: docs/api-convention.md docs/openapi.json
```

현재 브랜치에서 아직 커밋하지 않은 staged, unstaged, 관련 untracked 변경분을 1회 리뷰한다. 필요한 수정과 검증을 진행하며, 기본적으로 커밋하지 않는다.

```text
변경리뷰
$review-fix-test
```

마지막 커밋을 1회 리뷰한다. 필요한 follow-up 수정과 검증을 진행하며, 기본적으로 follow-up 커밋을 만든다.

```text
커밋리뷰
$review-fix-test commit
$review-fix-test target=commit
```

마지막 커밋과 현재 변경분을 함께 리뷰한다. 기본적으로 커밋하지 않는다.

```text
동시리뷰
$review-fix-test both
$review-fix-test target=both
```

반복 리뷰는 `max`로 지정한다. 반복 호출어의 기본 최대 반복은 10회다.

```text
반복리뷰
반복변경리뷰
반복커밋리뷰
반복변경리뷰 max=5
$review-fix-test 5
$review-fix-test commit 5
$review-fix-test both max=3
```

한 리뷰 사이클 안에서 검증 실패를 고치는 내부 반복은 `verify_max`로 지정한다. 기본값은 3이다.

```text
$review-fix-test verify_max=5
```

수정 없이 리뷰 결과만 받고 싶으면 `리뷰만`을 붙인다.

```text
변경리뷰 리뷰만
커밋리뷰 리뷰만
```

현재 변경분 리뷰는 기본적으로 커밋하지 않는다. 커밋까지 원하면 명시한다.

```text
변경리뷰 커밋까지
$review-fix-test commit=true
```

## Skill Format

각 skill은 `skills/<skill-name>/SKILL.md` 형태의 독립 폴더다. UI 메타데이터가 필요한 경우 `agents/openai.yaml`을 함께 둔다. skill 내부에는 별도 README나 changelog를 두지 않고, 공유/설치 안내는 repo root 문서에서 관리한다.

`instructions/`는 `AGENTS.md`가 참조하는 보조 지침이다. Codex의 명령 승인 정책용 `rules/`와 의미가 겹치지 않도록 일반 Markdown 지침은 이 폴더에 둔다.

## Development

- skill을 수정할 때는 `SKILL.md` frontmatter의 `name`과 `description`을 먼저 확인한다.
- 새 skill은 category 하위 폴더를 만들지 말고 `skills/<skill-name>/` 아래에 둔다.
- `review-fix-test`는 review workflow의 단일 엔진이다. 새 리뷰 호출어를 추가할 때는 skill을 늘리기보다 option parsing과 `instructions/skill-shortcuts.md` 매핑을 확장한다.
- 단축어나 커밋 규칙을 수정할 때는 `instructions/` 아래 파일을 먼저 수정한다.
- 공유 전 YAML frontmatter와 `agents/openai.yaml` 구문을 검증한다.
