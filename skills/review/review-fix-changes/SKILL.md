---
name: review-fix-changes
description: Run a subagent-backed review and fix workflow for the current uncommitted git changes instead of the latest commit. Use when the user invokes `$review-fix-changes` or asks in Korean for "변경리뷰", "작업트리 리뷰", "워킹트리 리뷰", "현재 변경 리뷰", "git 변경분 리뷰", "새 에이전트로 지금 변경된 것 리뷰", or similar. Spawn a new agent to review staged, unstaged, and relevant untracked changes for bugs, regressions, edge cases, and test consistency, then fix actionable issues and run relevant tests.
---

# Review Fix Changes

## Workflow

1. Inspect the repository state first: current branch, `git status --short`, staged diff, unstaged diff, and relevant untracked files.
2. Treat this skill invocation as an explicit request for a new agent. Spawn an `explorer` agent to review the current worktree changes unless subagents are unavailable. If the user says `리뷰만`, still use the explorer when possible, but do not edit or commit.
3. Ask the review agent to prioritize bugs, regressions, edge cases, test consistency, missing tests, data loss, security, concurrency, and meaningful performance risks. Tell it to avoid style-only comments unless they indicate a real maintenance risk.
4. Review the agent findings yourself. If fixes are needed and the scope is clear, either implement them locally or spawn a `worker` agent with a narrow file ownership scope. Tell workers they are not alone in the codebase, must not revert unrelated edits, and must not commit.
5. Run the smallest relevant test set that gives confidence. Broaden tests when the change touches shared behavior or public workflows.
6. Re-check `git diff`, `git diff --cached`, and `git status`. Do not revert user changes unrelated to this workflow.
7. Do not commit by default. Commit only if the user explicitly says `커밋까지`, `커밋해줘`, or similar. If committing, stage only the intended final changes and use Conventional Commits with Korean content. If the user says `리뷰만`, report findings only and do not edit or commit.

## One-Pass Result

End each run with a compact result that other review skills can reuse:

- `actionable_findings`: yes/no
- `fixes_applied`: yes/no
- `tests_run`: command list or `not run` with reason
- `remaining_risk`: concise note, or `none`

When this skill is used by `$review-fix-until-clean`, do not commit inside the one-pass run. Defer any final commit decision to `$review-fix-until-clean`.

## Explorer Prompt

Use this shape when delegating the review:

```text
현재 git 작업트리 변경분을 코드리뷰 관점으로 검토해라.
기준은 staged diff, unstaged diff, 그리고 관련 untracked 파일이다.
버그, 회귀, 엣지케이스, 테스트 누락/불일치를 최우선으로 보고,
보안/데이터 손상/동시성/성능 회귀 리스크가 있으면 함께 지적해라.
스타일 취향은 실제 유지보수 리스크가 있을 때만 언급해라.
수정하지 말고 findings만 심각도순으로 파일/라인 근거와 함께 보고해라.
```

## Worker Prompt

Use this shape only for bounded fixes:

```text
현재 작업트리 리뷰 findings 중 지정한 항목만 수정해라.
담당 파일 범위: <files>.
다른 에이전트/사용자 변경이 있을 수 있으니 관련 없는 변경을 되돌리지 마라.
직접 커밋하지 말고, 변경 파일과 실행한 테스트를 최종 보고해라.
```

## Commit Message

Commit only when explicitly requested. Prefer this format:

```text
fix: 현재 변경분 리뷰 반영
```

Adjust the type to match the final change, for example `test:`, `refactor:`, `docs:`, or `chore:`. Keep the content Korean unless the repository convention clearly requires otherwise.
