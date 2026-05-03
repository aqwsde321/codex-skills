# Codex Skills

개인 또는 팀에서 재사용할 수 있는 Codex skill 모음이다. 현재는 git 변경분과 마지막 커밋을 새 에이전트로 리뷰하고, 필요한 개선과 테스트까지 이어가는 리뷰 workflow skill을 포함한다.

## Skills

| Skill | 호출어 | 용도 |
| --- | --- | --- |
| `review-fix-changes` | `변경리뷰` | 현재 커밋하지 않은 변경분을 1회 리뷰/수정/테스트한다. |
| `review-fix-commit` | `커밋리뷰` | 마지막 커밋을 1회 리뷰/수정/테스트하고 필요한 follow-up 커밋을 만든다. |
| `review-fix-until-clean` | `반복변경리뷰`, `반복커밋리뷰` | fresh review pass에서 수정할 사항이 없을 때까지 반복한다. 기본 최대 10회다. |

## Repository Layout

```text
codex-skills/
├── AGENTS.md
├── AGENTS.snippet.md
├── LICENSE
├── README.md
└── skills/
    └── review/
        ├── review-fix-changes/
        │   ├── SKILL.md
        │   └── agents/
        │       └── openai.yaml
        ├── review-fix-commit/
        │   ├── SKILL.md
        │   └── agents/
        │       └── openai.yaml
        └── review-fix-until-clean/
            ├── SKILL.md
            └── agents/
                └── openai.yaml
```

`review-fix-until-clean`은 `review-fix-changes`를 sibling 경로로 참조한다. 따라서 review 계열 skill은 같은 부모 폴더 아래에 함께 둔다.

## Installation

### Manual Install

```bash
mkdir -p ~/.codex/skills
cp -R skills/review/review-fix-changes ~/.codex/skills/
cp -R skills/review/review-fix-commit ~/.codex/skills/
cp -R skills/review/review-fix-until-clean ~/.codex/skills/
```

설치 후 Codex를 재시작하면 skill 목록에 반영된다.

### Global Shortcuts

짧은 한국어 호출어를 쓰려면 `AGENTS.snippet.md` 내용을 전역 `~/.codex/AGENTS.md` 또는 프로젝트 `AGENTS.md`에 추가한다.

## Usage

현재 브랜치에서 아직 커밋하지 않은 staged, unstaged, 관련 untracked 변경분을 리뷰한다.

```text
변경리뷰
```

현재 변경분을 반복 리뷰한다. 기본 최대 반복은 10회다.

```text
반복변경리뷰
```

마지막 커밋을 리뷰하고 필요한 follow-up 수정을 커밋한다.

```text
커밋리뷰
```

마지막 커밋 기준으로 반복 리뷰한다. 기본 최대 반복은 10회다.

```text
반복커밋리뷰
```

반복 횟수는 요청에 함께 지정할 수 있다.

```text
반복변경리뷰 최대 5번
$review-fix-until-clean max=5
$review-fix-until-clean iterations=5
```

수정 없이 리뷰 결과만 받고 싶으면 `리뷰만`을 붙인다.

```text
변경리뷰 리뷰만
커밋리뷰 리뷰만
```

현재 변경분 리뷰는 기본적으로 커밋하지 않는다. 커밋까지 원하면 명시한다.

```text
변경리뷰 커밋까지
```

## Skill Format

각 skill은 `SKILL.md`를 포함한 독립 폴더다. UI 메타데이터가 필요한 경우 `agents/openai.yaml`을 함께 둔다. skill 내부에는 별도 README나 changelog를 두지 않고, 공유/설치 안내는 repo root 문서에서 관리한다.

## Development

- skill을 수정할 때는 `SKILL.md` frontmatter의 `name`과 `description`을 먼저 확인한다.
- review 계열 skill은 같은 부모 폴더 아래 sibling 관계를 유지한다.
- `review-fix-until-clean`은 현재 변경분 반복 회차에서 `$review-fix-changes`를 재사용한다.
- 공유 전 YAML frontmatter와 `agents/openai.yaml` 구문을 검증한다.

## License

MIT
