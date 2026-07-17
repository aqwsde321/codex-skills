# Codex Skills

자주 쓰는 workflow만 유지하는 Codex skill 모음이다. Matt Pocock 원본 5개와 프로젝트 고유 skill을 함께 둔다.

## Skills

| Skill | 한국어 호출어 | 용도 |
| --- | --- | --- |
| `grill-me` + `grilling` | `설계리뷰` | 계획의 미확정 결정을 한 질문씩 검증한다. |
| `diagnosing-bugs` | `진단` | 재현 가능한 red-capable feedback loop부터 버그 원인을 좁힌다. |
| `tdd` | `TDD` | 합의한 seam에서 한 테스트와 한 구현의 vertical slice를 반복한다. |
| `code-review` | `코드리뷰` | fixed point부터 `HEAD`까지 Standards와 Spec을 병렬 리뷰한다. |
| `feature-flow-review` | `기능플로우리뷰` | 다단계 기능의 분기, 상태 전이, 외부 연동을 정리한다. |
| `api-design-review` | `API리뷰` | 확정된 플로우를 API 엔드포인트와 edge case로 정리한다. |
| `project-context` | `프로젝트 컨텍스트 세팅` | codebase-memory와 source-grounded 프로젝트 문서를 준비한다. |
| `simplification-debt` | `단순화부채` | `ponytail:` 주석의 한계와 재검토 조건을 모은다. |
| `solution-capture` | `해결기록` | 확인된 해결 지식을 `docs/solutions/`에 기록한다. |

번호 호출어는 사용하지 않는다. 전체 별칭과 라우팅은 `instructions/skill-shortcuts.md`에 있다.

## Upstream Scope

아래 디렉터리는 `mattpocock/skills@9603c1cc8118d08bc1b3bf34cf714f62178dea3b` 원본이다.

- `grill-me`
- `grilling`
- `diagnosing-bugs`
- `tdd`
- `code-review`

원본 파일은 현지화하지 않는다. 한국어 별칭은 instruction 파일에서만 관리한다.

`code-review`는 fixed point 기준 보고 전용이며 미커밋 작업트리 리뷰, 자동 수정, 테스트, 커밋, 반복 옵션을 제공하지 않는다. 그런 작업은 일반 요청으로 별도 수행한다.

`code-review` 원본은 이슈 조회 시 `docs/agents/issue-tracker.md` 또는 `setup-matt-pocock-skills`를 기대한다. 최소 구성을 위해 setup skill은 포함하지 않았다. 필요하면 spec 경로를 직접 제공하거나 setup skill을 별도 설치한다.

## Repository Layout

```text
codex-skills/
├── AGENTS.md
├── README.md
├── docs/
│   └── solutions/
│       └── README.md
├── hooks/
│   └── turn_usage_summary.py
├── instructions/
│   ├── docs.md
│   ├── git.md
│   └── skill-shortcuts.md
└── skills/
    ├── api-design-review/
    ├── code-review/
    ├── diagnosing-bugs/
    │   └── scripts/
    │       └── hitl-loop.template.sh
    ├── feature-flow-review/
    ├── grill-me/
    ├── grilling/
    ├── project-context/
    │   └── scripts/
    ├── simplification-debt/
    │   └── scripts/
    ├── solution-capture/
    └── tdd/
        ├── mocking.md
        └── tests.md
```

각 skill에는 `SKILL.md`가 있고, UI 메타데이터가 필요하면 `agents/openai.yaml`도 둔다.

## Installation

기존 설치를 교체한다면 옛 디렉터리를 먼저 빈 백업 경로로 이동한다.

```bash
retired=$(mktemp -d /tmp/codex-skills-retired.XXXXXX)
for name in plan-grill diagnose tdd zoom-out review-fix-test; do
  if [ -d ~/.codex/skills/"$name" ]; then
    mv ~/.codex/skills/"$name" "$retired"/
  fi
done
```

```bash
mkdir -p ~/.codex/skills ~/.codex/instructions
cp -R skills/* ~/.codex/skills/
cp instructions/git.md ~/.codex/instructions/
cp instructions/skill-shortcuts.md ~/.codex/instructions/
```

다음 Codex task부터 새 skill 목록이 반영된다.

`solution-capture`를 프로젝트에서 쓰려면 해당 프로젝트에 `docs/solutions/`를 두고, 가능하면 이 저장소의 `docs/solutions/README.md` 규칙을 적용한다.

## Usage

```text
설계리뷰
진단
TDD
코드리뷰 main
기능플로우리뷰
API리뷰
프로젝트 컨텍스트 세팅
단순화부채
해결기록
```

`코드리뷰`에는 `main`, `HEAD~1`, tag 같은 fixed point를 준다. 없으면 skill이 질문한다.

## Turn Usage Hook

턴 종료 시 현재 turn 토큰, 현재 대화 context 비율, 계정 전체 5시간/7일 quota 잔여율을 보고 싶으면 전역 hook으로 설치한다. 전역 설정은 한 번만 하면 다른 프로젝트에서도 적용된다.

```bash
mkdir -p ~/.codex/hooks
cp hooks/turn_usage_summary.py ~/.codex/hooks/turn_usage_summary.py
```

`~/.codex/config.toml`에 Stop hook을 추가한다.

```toml
# Turn usage summary hook
[[hooks.Stop]]
[[hooks.Stop.hooks]]
type = "command"
command = "python3 /Users/<user>/.codex/hooks/turn_usage_summary.py"
timeout = 5
```

Codex가 hook을 untrusted로 표시하면 Hooks 설정에서 trust한다. 이미 `~/.codex/config.toml`에 hook을 쓰고 있다면 `~/.codex/hooks.json`에는 hook을 두지 않는다. 같은 layer에서 `hooks.json`과 `config.toml` hook을 동시에 쓰면 `loading hooks from both ...; prefer a single representation for this layer` 경고가 난다.

`acct left`의 5시간/7일 quota 값은 계정 전체 잔여율이라 다른 대화와 프로젝트 사용량이 반영된다. 대화별 사용량으로 해석하지 않는다.

출력 예:

```text
Turn: 7,000 tok; ctx 9.93%; acct left 5h 96%, 7d 99%
```

## Global Instructions

`~/.codex/AGENTS.md` 또는 프로젝트 `AGENTS.md`에서 instruction 파일을 참조한다.

```md
## Additional Instructions

- Git/커밋 메시지 규칙은 `~/.codex/instructions/git.md`를 따른다.
- 스킬 호출어와 실행 보조 규칙은 `~/.codex/instructions/skill-shortcuts.md`를 따른다.
```

## Development

- upstream skill 갱신은 commit SHA를 먼저 바꾸고 원본 디렉터리를 통째로 교체한다.
- 원본 skill 내부에는 한국어 호출어나 로컬 실행 규칙을 추가하지 않는다.
- 로컬 skill은 `skills/<skill-name>/` 아래에 둔다.
- 단축어는 `instructions/skill-shortcuts.md`에서만 관리한다.
- 공유 전 YAML frontmatter, `agents/openai.yaml`, upstream 파일 해시를 검증한다.
