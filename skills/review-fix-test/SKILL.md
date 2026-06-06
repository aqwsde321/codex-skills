---
name: review-fix-test
description: Single subagent-backed git review workflow that reviews, fixes, verifies, and optionally commits current changes, the latest commit, or both, checking core risk plus optional Standards and Spec review axes. Use when invoked as `$review-fix-test` or through Korean shortcuts such as "40리뷰", "변경리뷰", "커밋리뷰", "동시리뷰", "반복리뷰", "반복변경리뷰", "반복커밋리뷰", or similar. Supports target=changes|commit|both, positional shorthands like `commit 5`, max review cycles, and verify_max validation retries.
---

# Review Fix Test

## Defaults

Use these defaults unless the user overrides them:

- `target=changes`
- `max=1`
- `verify_max=3`
- `commit=false` for `target=changes`
- `commit=true` for `target=commit`
- `commit=false` for `target=both`

If the user says `리뷰만`, set `review_only=true`: run explorer review and report findings, but do not edit, verify, or commit.

## Option Parsing

Accept canonical options:

```text
$review-fix-test target=changes max=5 verify_max=3 commit=false
$review-fix-test target=commit max=5
$review-fix-test target=both max=3
$review-fix-test spec=docs/features/example.md
$review-fix-test standards=AGENTS.md,docs/adr
$review-fix-test 기준문서: AGENTS.md docs/adr
```

Accept positional shorthands:

```text
$review-fix-test
$review-fix-test 5
$review-fix-test changes
$review-fix-test changes 5
$review-fix-test commit
$review-fix-test commit 5
$review-fix-test both
$review-fix-test both 5
$review-fix-test 변경 5
$review-fix-test 커밋 5
$review-fix-test 동시 5
```

Map Korean shortcuts:

- `40리뷰`: `target=changes max=1`
- `변경리뷰`: `target=changes max=1`
- `커밋리뷰`: `target=commit max=1`
- `동시리뷰`: `target=both max=1`
- `반복변경리뷰`: `target=changes max=10`
- `반복커밋리뷰`: `target=commit max=10`
- `반복리뷰`: `target=changes max=10`

If the user adds a number or `max=<n>` to a shortcut, use that value instead of the shortcut default. Examples:

```text
반복변경리뷰 5
반복변경리뷰 max=5
커밋리뷰 3
동시리뷰 max=3
```

Ask for clarification before starting when target values conflict, numeric values are invalid, or the request gives contradictory `commit` values. If `max` or `verify_max` is greater than 20, confirm before using it.

## Targets

For `target=changes`, review current uncommitted git changes:

```text
git diff --cached
git diff
relevant untracked files from git status --short
```

For `target=commit`, review the latest commit:

```text
git show --stat --patch HEAD
```

For `target=both`, review both targets as separate sections. Keep findings labeled as `commit`, `changes`, or `both` so the main agent can avoid mixing scopes.

## Review Axes

Always run the Core Risk axis. Add Standards and Spec axes when evidence exists.

### Core Risk

Review for:

- Bugs and behavioral regressions
- Edge cases and invalid inputs
- Test mismatch, missing tests, or brittle tests
- Data loss, security, concurrency, and meaningful performance risks
- Changes that violate the request or local codebase contracts

### Standards

Use this axis when the repository has documented project standards or the user provides `standards=<path[,path...]>` or Korean hints such as `기준문서:`.

Collect standards sources from:

- `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`
- `docs/adr/`, `docs/**/ADR*`, `docs/**/*standard*`, `docs/**/*convention*`
- `STYLE.md`, `STANDARDS.md`, `STYLEGUIDE.md`, or similar files
- `.editorconfig`, lint, format, typecheck, and build config files as supporting evidence

Do not re-check what automated tooling already verifies. Use config files to understand conventions, then rely on verification commands for machine-enforced rules.

### Spec

Use this axis when the originating requirement is available.

Find the spec source in this order:

1. User-provided `spec=<path>` or Korean hints such as `스펙:`, `요구사항:`, `기획서:`, `PRD:`.
2. A local PRD, issue, requirement, or spec document under `docs/`, `specs/`, or `.scratch/` that clearly matches the branch name, touched feature, or user request.
3. Commit messages that reference a local issue/spec file.

If no spec is available, skip the Spec axis and say so. Do not ask the user for a spec unless the review cannot be meaningfully judged without one.

## Review Cycle

Run up to `max` review cycles. One cycle is:

1. Inspect repository state: current branch, `git status --short`, the selected target diff, and available Standards/Spec sources.
2. Spawn a fresh `explorer` agent to review the selected target across the active review axes. The explorer must not edit files.
3. Main agent triages explorer findings. Fix only actionable issues grounded in the target diff or necessary surrounding code. Discard style-only comments unless they indicate real maintenance risk.
4. Main agent applies the minimal necessary fix. Do not spawn a `worker` agent for fixes unless the user explicitly asks for worker delegation.
5. Main agent runs verification. If verification fails, repeat fix -> verification up to `verify_max` times inside the same cycle.
6. After verification passes, spawn a fresh `explorer` agent for a post-fix review of the updated effective changeset.
7. Stop when the post-fix review reports no actionable findings. Otherwise start the next cycle if `max` allows it.

If a cycle has no actionable findings in the initial explorer review, stop after reporting the clean result. If `review_only=true`, stop after the initial review regardless of findings.

## Triage Criteria

Prioritize Core Risk findings first, then Standards violations, then Spec mismatches.

Treat a Standards or Spec finding as actionable only when it cites a concrete source and the change clearly violates it.

Avoid style or preference comments unless they create a concrete maintainability risk.

## Verification

Choose the smallest relevant verification that gives confidence:

- Targeted unit tests for isolated logic
- Focused integration tests for cross-module behavior
- Existing format/typecheck/build commands when the touched area requires them

When verification fails:

1. Read the failure.
2. Fix only the cause connected to this workflow.
3. Re-run the same verification.
4. Stop after `verify_max` failed attempts and report the remaining blocker.

Do not commit if verification is failing or blocked.

## Explorer Prompt

Use this shape for initial and post-fix explorer reviews:

```text
대상: <changes|commit|both>
리뷰 사이클: <N>/<max>
Standards sources: <none|file/dir list with relevant excerpts or line references>
Spec source: <none|file path with relevant excerpts or line references>

선택된 git 변경분을 코드리뷰 관점으로 검토해라.
활성 리뷰 축:
- Core Risk: 항상 검토한다.
- Standards: standards sources가 있으면 문서화된 기준 위반만 지적한다.
- Spec: spec source가 있으면 요구사항 누락, 부분 구현, scope creep, 잘못 구현된 요구사항을 지적한다.

버그, 회귀, 엣지케이스, 테스트 누락/불일치를 최우선으로 보고,
보안/데이터 손상/동시성/성능 회귀 리스크가 있으면 함께 지적해라.
스타일 취향은 실제 유지보수 리스크가 있을 때만 언급해라.
Standards와 Spec finding은 기준 문서나 spec source를 함께 인용해라.
수정하지 말고 actionable findings만 심각도순으로 파일/라인 근거와 함께 보고해라.
target=both이면 finding마다 commit/changes/both 범위를 표시해라.
수정할 actionable finding이 없으면 "수정할 사항 없음"이라고 명확히 말해라.
```

## Commit Policy

Commit only after the final review is clean and verification passes.

Default commit behavior:

- `target=changes`: do not commit unless the user sets `commit=true`, says `커밋까지`, or says `커밋해줘`.
- `target=commit`: commit follow-up fixes by default.
- `target=both`: do not commit unless the user explicitly sets `commit=true`, says `커밋까지`, or says `커밋해줘`.

When committing, stage only intended final changes from this workflow and use Conventional Commits with Korean content:

```text
fix: 리뷰 결과 반영
```

Adjust the type to match the final change, for example `test:`, `refactor:`, `docs:`, or `chore:`.

## Final Report

End with:

- Effective options: `target`, `max`, `verify_max`, `commit`, and actual cycle count
- Active review axes and Standards/Spec sources used or skipped
- Findings fixed or "수정할 사항 없음"
- Verification commands and results
- Commit hash if a commit was created
- Remaining risk or blocker, if any
- If the review/fix uncovered a reusable project lesson, recurring bug pattern, tool setup detail, or non-obvious verification approach, suggest `$solution-capture` in one sentence. Do not create the solution note unless the user confirms.
