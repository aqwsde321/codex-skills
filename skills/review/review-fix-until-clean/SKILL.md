---
name: review-fix-until-clean
description: Run an iterative subagent-backed review, fix, and test loop until a fresh review pass reports no actionable fixes. Use when the user invokes `$review-fix-until-clean` or asks in Korean for "반복변경리뷰", "반복커밋리뷰", "반복리뷰", "끝까지 리뷰", "수정할 거 없을 때까지 리뷰", "더 이상 수정할 거 없을 때까지", "새 에이전트로 계속 리뷰하고 수정", or similar. Default to current uncommitted git changes and a maximum of 10 iterations; use the latest commit target when the user explicitly says "반복커밋리뷰", "마지막 커밋", or "커밋 기준".
---

# Review Fix Until Clean

## Workflow

1. Determine the target:
   - Current changes by default, or when the user says `반복변경리뷰`: staged diff, unstaged diff, and relevant untracked files.
   - Latest commit when the user explicitly says `반복커밋리뷰`, `마지막 커밋`, `커밋 기준`, or invokes this with `$review-fix-commit`.
2. Determine `max_iterations` before starting. Default to 10. Accept user overrides such as `최대 5번`, `5회까지만`, `max=5`, `max iterations 5`, or `iterations=5`.
3. For current changes, use `$review-fix-changes` as the one-pass review/fix/test operation for every iteration. Read and follow `../review-fix-changes/SKILL.md` when needed instead of duplicating its review prompt or fix policy.
4. Run iteration 1 by executing one `$review-fix-changes` pass with this override: do not commit inside the pass, even if the user asked for `커밋까지`; defer commit until the loop is clean.
5. Inspect the one-pass result from `$review-fix-changes`:
   - Stop when `actionable_findings: no` and `remaining_risk: none`.
   - Repeat when `fixes_applied: yes` or actionable findings remain after fixes.
   - Stop under the safety rules below when the pass cannot make progress.
6. For each repeat, run a fresh `$review-fix-changes` pass against the updated current changes. Treat this skill invocation as explicit permission to use new subagents on each pass.
7. For latest-commit targets, do not use `$review-fix-changes` for the initial pass because the review target is different. Review the latest commit first, then use the current-changes loop for follow-up fixes if needed.

## Iteration Limit

Use 10 as the default maximum number of review iterations.

Recognize these override forms:

```text
반복리뷰 최대 5번
반복리뷰 5회까지만
$review-fix-until-clean max=5
$review-fix-until-clean iterations=5
```

If the user provides a non-positive, non-numeric, or contradictory limit, ask for clarification before starting. If the user provides an unusually high limit over 20, confirm before using it.

## Safety Stops

Stop and report remaining risk instead of looping indefinitely when any of these happens:

- The same finding survives two fix attempts.
- A finding requires product/design clarification that cannot be inferred safely.
- The configured `max_iterations` limit is reached.
- Required tests cannot run because of environment, dependency, or permission blockers.

## Target Details

For current changes, the effective changeset is:

```text
git diff --cached
git diff
relevant untracked files from git status --short
```

The current-changes loop should inherit target details, review criteria, worker constraints, test selection, and one-pass reporting from `$review-fix-changes`.

For latest commit, the first review target is:

```text
git show --stat --patch HEAD
```

After any fixes for a latest-commit review, subsequent iterations must review the latest commit plus current follow-up fixes as one effective changeset:

```text
git show --stat --patch HEAD
git diff --cached
git diff
relevant untracked files from git status --short
```

## Explorer Prompt

Use this shape when delegating each review iteration:

```text
반복 리뷰 루프의 <N>회차다.
대상 변경분을 코드리뷰 관점으로 검토해라.
버그, 회귀, 엣지케이스, 테스트 누락/불일치를 최우선으로 보고,
보안/데이터 손상/동시성/성능 회귀 리스크가 있으면 함께 지적해라.
스타일 취향은 실제 유지보수 리스크가 있을 때만 언급해라.
수정하지 말고 actionable findings만 심각도순으로 파일/라인 근거와 함께 보고해라.
수정할 actionable finding이 없으면 "수정할 사항 없음"이라고 명확히 말해라.
```

## Worker Prompt

Use this shape only for bounded fixes:

```text
반복 리뷰 <N>회차 findings 중 지정한 항목만 수정해라.
담당 파일 범위: <files>.
다른 에이전트/사용자 변경이 있을 수 있으니 관련 없는 변경을 되돌리지 마라.
직접 커밋하지 말고, 변경 파일과 실행한 테스트를 최종 보고해라.
```

## Commit Policy

Do not commit by default for current-changes reviews. Commit only if the user explicitly says `커밋까지`, `커밋해줘`, or similar.

For latest-commit reviews, commit the final follow-up fixes when the user asked for the full review/fix/commit workflow. Use Conventional Commits with Korean content.

Prefer these message shapes:

```text
fix: 반복 리뷰 결과 반영
```

```text
test: 반복 리뷰 테스트 보강
```
