---
name: solution-capture
description: Capture solved problems, debugging outcomes, project-specific decisions, or reusable workflow patterns as durable Markdown notes under docs/solutions. Use when invoked as `$solution-capture` or through Korean shortcuts such as "해결기록", "해결지식", "지식축적", "컴파운드", "문제 해결 기록", or when the user asks to document lessons learned after fixing, debugging, reviewing, or setting up something.
---

# Solution Capture

## Core Rule

Create durable knowledge only when there is a solved problem, hard-won debugging result, project-specific decision, or reusable workflow pattern.

Do not run this skill just because another workflow found a possible reusable lesson. Other skills may suggest `$solution-capture`, but create or update a note only after the user explicitly confirms or directly invokes this skill.

Do not create a solution document for trivial edits, generic advice, or unresolved speculation unless the user explicitly asks for a draft.

## Inputs

Use the best available evidence:

- The recent conversation and user request
- `git status --short`, diffs, and touched files when relevant
- Test output, logs, stack traces, or command output already available
- Existing docs under `docs/solutions/`

If the root cause, final fix, or verification is unclear, ask one concise question before writing.

## Workflow

1. Identify the reusable lesson:
   - What problem was solved?
   - What made it non-obvious?
   - What future task should benefit from this note?
2. Search for an existing related note:
   - Use `rg` under `docs/solutions/` for module names, symptoms, error text, commands, and tags.
   - If a matching note exists, update it instead of creating a duplicate.
3. Choose a category:
   - `runtime-errors`
   - `test-failures`
   - `workflow-issues`
   - `tool-setup`
   - `design-decisions`
   - `best-practices`
   - `performance`
   - `security`
4. Write the note under `docs/solutions/<category>/`.
5. Keep the note concise and evidence-backed. Include failed attempts only when they prevent future wasted work.
6. Redact secrets, tokens, credentials, private URLs, and sensitive personal data.
7. Report the created or updated file path and the one-line reusable lesson.

## File Naming

Use lowercase kebab-case:

```text
docs/solutions/<category>/<short-problem-or-pattern>.md
```

If the name would collide with an unrelated note, append a short qualifier.

## Frontmatter

Use YAML frontmatter:

```yaml
---
title: Short solution title
date: YYYY-MM-DD
category: runtime-errors
module: module-or-area
problem_type: runtime_error
component: component-or-workflow
severity: low|medium|high
tags: [tag-one, tag-two]
related_files:
  - path/to/file.ext
---
```

Use `unknown` only when a field is genuinely unclear and asking would not materially improve the note.

## Body Template

Use these sections, omitting sections that do not apply:

```markdown
## Problem

## Symptoms

## Root Cause

## Solution

## What Did Not Work

## Verification

## Prevention

## Reuse Checklist
```

## Update Policy

When updating an existing note:

- Preserve still-accurate historical context.
- Add dated updates only when the new finding changes or narrows the old lesson.
- Remove or mark outdated guidance when the new result proves it wrong.
- Do not rewrite unrelated sections for style.

## Final Report

End with:

- Created or updated file path
- Category and tags
- One-line reusable lesson
- Any uncertainty that remains
