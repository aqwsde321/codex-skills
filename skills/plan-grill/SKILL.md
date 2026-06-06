---
name: plan-grill
description: Stress-test a plan, design, feature idea, or implementation approach by asking one focused question at a time until the risky branches and assumptions are resolved. Use when invoked as `$plan-grill` or through Korean shortcuts such as "10설계", "설계리뷰", "계획압박", "그릴", "grill", "허점 찾아줘", "질문으로 털어줘", "계획 검증", or when the user wants to be interviewed before implementation without automatically writing CONTEXT.md or ADR documents.
---

# Plan Grill

## Core Rule

Ask one question at a time. For each question, include the recommended answer and why it matters.

Do not write implementation code, API specs, `CONTEXT.md`, ADRs, or solution notes in this skill unless the user explicitly asks after the grill is complete.

## When To Handoff

Use `$feature-flow-review` instead when the user already wants a structured feature flow with user branches, state transitions, tokens, temporary storage, approvals, payment, settlement, account linking, or external integrations.

Use `$api-design-review` instead when the flow is already confirmed and the user wants endpoint, request, response, or API edge-case design.

Use `$zoom-out` first when the plan depends on unfamiliar code structure and the relevant modules or callers are not understood yet.

## Workflow

1. State the current plan in one short paragraph.
2. Identify the riskiest unresolved branch.
3. Ask exactly one question.
4. Include:
   - Why this question matters
   - Recommended answer
   - Consequence if the recommendation is wrong
5. Wait for the user answer.
6. Use the answer to update the working understanding.
7. Repeat until the plan is clear enough to hand off.

If the question can be answered by reading repository files, inspect the code instead of asking the user. Report the evidence and move to the next question.

## Question Priority

Prefer questions in this order:

1. Goal and success criteria
2. User types, permissions, and ownership
3. State transitions and invalid states
4. Data lifetime, idempotency, and rollback
5. External systems, retries, and failure modes
6. Security, privacy, and authorization boundaries
7. Migration, compatibility, and rollout
8. Test strategy and verification gates
9. Naming, domain terms, and ambiguity

## Stop Conditions

Stop when one of these is true:

- The risky branches are resolved enough for implementation planning.
- The remaining questions belong to `$feature-flow-review`, `$api-design-review`, `$diagnose`, or `$zoom-out`.
- The user says to stop, proceed, or switch modes.

End by summarizing:

- Resolved decisions
- Remaining assumptions
- Recommended next skill or next action

If the grill resolved a reusable project-specific decision, recurring design rule, or non-obvious tradeoff, suggest `$solution-capture` in one sentence. Do not create the solution note unless the user confirms.
