---
name: review-fix-commit
description: Run a subagent-backed latest commit review, fix, test, and commit workflow. Use when the user invokes `$review-fix-commit` or asks in Korean for "커밋리뷰", "리뷰커밋", "막커밋 리뷰", "마지막 커밋 리뷰하고 수정", "새 에이전트로 마지막 커밋 리뷰하고 문제 있으면 수정 후 커밋", or similar. Spawn a new agent to review bugs, regressions, edge cases, and test consistency, have actionable fixes implemented, then verify and create a Korean Conventional Commit.
---

# Review Fix Commit

## Workflow

1. Inspect the repository state first: current branch, dirty files, and the latest commit diff.
2. Treat this skill invocation as an explicit request for a new agent. Spawn an `explorer` agent to review the latest commit unless subagents are unavailable. If the user says `리뷰만`, still use the explorer when possible, but do not edit or commit.
3. Ask the review agent to prioritize bugs, regressions, edge cases, test consistency, missing tests, data loss, security, concurrency, and meaningful performance risks. Tell it to avoid style-only comments unless they indicate a real maintenance risk.
4. Review the agent findings yourself. If fixes are needed and the scope is clear, either implement them locally or spawn a `worker` agent with a narrow file ownership scope. Tell workers they are not alone in the codebase, must not revert unrelated edits, and must not commit.
5. Run the smallest relevant test set that gives confidence. Broaden tests when the change touches shared behavior or public workflows.
6. Re-check `git diff` and `git status`. Do not revert user changes unrelated to this workflow.
7. Commit the final changes from the main agent after reviewing the integrated diff and test result. Use Conventional Commits with Korean content. If the user says `리뷰만`, report findings only and do not edit or commit.

## Explorer Prompt

Use this shape when delegating the review:

```text
마지막 커밋 diff를 코드리뷰 관점으로 검토해라.
버그, 회귀, 엣지케이스, 테스트 누락/불일치를 최우선으로 보고,
보안/데이터 손상/동시성/성능 회귀 리스크가 있으면 함께 지적해라.
스타일 취향은 실제 유지보수 리스크가 있을 때만 언급해라.
수정하지 말고 findings만 심각도순으로 파일/라인 근거와 함께 보고해라.
```

## Worker Prompt

Use this shape only for bounded fixes:

```text
리뷰 findings 중 지정한 항목만 수정해라.
담당 파일 범위: <files>.
다른 에이전트/사용자 변경이 있을 수 있으니 관련 없는 변경을 되돌리지 마라.
직접 커밋하지 말고, 변경 파일과 실행한 테스트를 최종 보고해라.
```

## Commit Message

Prefer this format:

```text
fix: 마지막 커밋 리뷰 반영
```

Adjust the type to match the final change, for example `test:`, `refactor:`, `docs:`, or `chore:`. Keep the content Korean unless the repository convention clearly requires otherwise.
