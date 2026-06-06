---
name: diagnose
description: Disciplined bug and performance diagnosis workflow centered on a fast reproducible feedback loop. Use when invoked as `$diagnose` or through Korean shortcuts such as "20진단", "진단", "디버깅", "버그진단", "원인분석", "재현부터", or when the user reports failing, broken, throwing, flaky, slow, or regressed behavior and wants the cause found before changing code.
---

# Diagnose

## Core Rule

Do not guess at the fix before proving the symptom with a feedback loop.

The feedback loop can be a failing test, a CLI command, an HTTP request, a browser script, a replayed payload, a small harness, or a repeated stress loop for flaky behavior.

## Workflow

1. Define the user-reported symptom in concrete terms:
   - Expected behavior
   - Actual behavior
   - Command, request, UI path, input, log, or stack trace that shows it
2. Build the smallest useful feedback loop:
   - Prefer a failing test when the codebase has a correct seam.
   - Use a targeted command, curl request, script, or harness when a test is not yet practical.
   - For flaky bugs, increase reproduction rate with repetition, stress, fixed seeds, or narrowed timing windows.
3. Reproduce the exact symptom:
   - Confirm it matches the user's report, not a nearby failure.
   - Capture the assertion, error text, output diff, or timing baseline.
4. List 3-5 ranked hypotheses before editing production code.
   - Each hypothesis must include a prediction that can be disproved.
   - Test one variable at a time.
5. Instrument only where the hypothesis needs evidence.
   - Prefer debuggers, REPL inspection, targeted logs, query plans, profilers, or narrow assertions.
   - Tag temporary logs with a unique prefix such as `[DEBUG-a4f2]`.
   - Do not add broad "log everything" instrumentation.
6. Decide the implementation handoff.
   - If the user asked only for diagnosis, stop after root cause, reproduction, and recommended fix direction.
   - If the user asked to fix in the same task, use the `$tdd` red-green-refactor loop for the smallest root-cause fix once the cause is understood.
   - If a correct test seam exists, turn the minimized reproduction into a failing regression test before the fix.
   - If no correct seam exists, document that limitation instead of adding a shallow false-confidence test.
7. Verify and clean up:
   - Re-run the original feedback loop.
   - Re-run the regression test or targeted verification.
   - Remove temporary logs, harnesses, and debug artifacts unless they are intentionally kept in a clearly named location.
   - Search for the debug prefix before finishing.

## JPA And Transaction Bugs

For `LazyInitializationException`, stale entity, missing dirty checking, bulk update/delete, or transaction-boundary issues, follow the repository JPA/Transaction bug-fix rules in `AGENTS.md`.

Do not switch fetch strategy, add `JOIN FETCH`, add `@EntityGraph`, or change `@Modifying(clearAutomatically = true)` behavior until the transaction boundary and reproduction are understood.

## When No Loop Is Possible

Stop and state what was tried. Ask for the missing artifact that would make diagnosis possible:

- Reproduction steps
- Logs or stack trace
- Example payload or fixture
- HAR file or screen recording
- Access to an environment that reproduces the issue
- Permission to add temporary instrumentation

## Final Report

End with:

- Feedback loop used
- Reproduced symptom
- Root cause
- Fix summary
- Verification commands and results
- Regression test status or why no correct seam exists
- Cleanup performed
- If the result produced reusable learning, suggest `$solution-capture` in one sentence. Do not create the solution note unless the user confirms.

Suggest `$solution-capture` when any of these are true:

- The root cause was non-obvious.
- The fix involved a project-specific convention, tool setup, transaction boundary, flaky behavior, or performance diagnosis.
- A failed hypothesis or failed attempt would save future debugging time.
- The same symptom is likely to recur.
