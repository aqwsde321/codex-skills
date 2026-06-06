---
name: tdd
description: Test-driven development workflow using a small red-green-refactor loop through public behavior, with a lightweight domain modeling checkpoint for domain-driven design. Use when invoked as `$tdd` or through Korean shortcuts such as "30구현", "TDD", "테스트우선", "테스트 먼저", "red-green-refactor", or when the user asks to build a feature test-first or fix a reproduced bug test-first after the cause is understood.
---

# TDD

## Core Rule

Write one behavior test, make it fail for the right reason, write the smallest implementation that makes it pass, then repeat.

Do not write a pile of speculative tests before implementation.

## Test Quality

Good tests verify observable behavior through public interfaces. They should keep passing when internals are refactored without behavior changes.

Avoid tests that primarily verify private methods, internal collaborator calls, implementation-specific DTO construction, or database state through a back door when a public interface can prove the behavior.

Use mocks only at real external boundaries, such as network APIs, clocks, queues, payment gateways, email/SMS providers, or expensive infrastructure that the test cannot reasonably run.

## Domain Modeling Checkpoint

Before writing the first test for domain behavior, identify:

- Domain terms from the user request, existing code, and project documents.
- Business rules and invariants that must always hold.
- The likely owner of each rule: entity, value object, aggregate, domain service, application service, or adapter.
- Aggregate or transaction boundary assumptions when state changes must stay consistent.

Prefer putting domain rules in the domain model. Keep application services focused on orchestration, transactions, authorization checks, and integration calls.

Do not create DDD abstractions just because the terminology exists. Add entities, value objects, aggregates, repositories, factories, or domain services only when the current behavior needs them to express, test, or protect a real business rule.

## Workflow

1. Plan the next vertical slice:
   - Identify the public interface being changed.
   - Confirm the domain terms, invariants, and rule owner for this slice.
   - List behavior outcomes, not implementation steps.
   - Prioritize one critical behavior first.
   - State assumptions before editing.
2. Red:
   - Add one focused test for the next behavior.
   - Run it and confirm it fails for the expected reason.
3. Green:
   - Add only enough production code to pass that test.
   - Do not add speculative options, abstractions, or future behaviors.
4. Repeat:
   - Add the next behavior test only after the previous test is green.
   - Let each cycle update the plan based on what the code revealed.
5. Refactor:
   - Refactor only while green.
   - Keep changes behavior-preserving.
   - Re-run the relevant tests after each meaningful refactor.

## Bug Fixes

For bugs, use `$diagnose` first when the symptom is not reproduced yet.

Once the cause is understood, convert the minimized reproduction into a regression test at the most realistic seam, then fix.

## Stop Conditions

Stop the loop when one of these is true:

- The requested vertical slice has all critical behavior tests green.
- The next behavior depends on an unresolved product, API, or domain decision.
- The remaining work is refactoring beyond the requested behavior.
- Verification is blocked after reporting the failing command and reason.

## Per-Cycle Checklist

```text
[ ] Test describes user-observable behavior
[ ] Domain terms and invariants are named explicitly when the behavior is domain-specific
[ ] Test reaches the real code path
[ ] Test fails for the expected reason
[ ] Implementation is minimal for this behavior
[ ] Domain-specific rules are not hidden only in orchestration code when a clearer domain owner already exists
[ ] No speculative feature or abstraction was added
[ ] Relevant tests pass before the next cycle
```

## Final Report

End with:

- Behaviors covered
- Domain terms, invariants, or ownership decisions changed
- Tests added or updated
- Implementation summary
- Verification commands and results
- Remaining behavior gaps or tradeoffs
- If the cycle revealed a reusable testing pattern, project convention, or non-obvious test seam, suggest `$solution-capture` in one sentence. Do not create the solution note unless the user confirms.
