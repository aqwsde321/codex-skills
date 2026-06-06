# Documented Solutions

This directory stores durable notes about solved problems, debugging outcomes, and reusable workflow patterns.

Create or update solution documents only after the user explicitly asks for `해결기록` / `$solution-capture` or confirms a suggestion from another workflow.

Use one of these category subdirectories:

- `runtime-errors/`
- `test-failures/`
- `workflow-issues/`
- `tool-setup/`
- `design-decisions/`
- `best-practices/`
- `performance/`
- `security/`

Before creating a new note, search existing notes for module names, symptoms, error text, commands, and tags. Update a matching note instead of creating a duplicate.

Use lowercase kebab-case filenames:

```text
docs/solutions/<category>/<short-problem-or-pattern>.md
```

Use Markdown files with YAML frontmatter fields that make the note searchable:

```yaml
---
title: Short solution title
date: YYYY-MM-DD
category: best-practices
module: module-or-area
problem_type: best_practice
component: development_workflow
severity: low
tags: [keyword-one, keyword-two]
related_files:
  - path/to/file.ext
---
```

Keep notes concise and evidence-backed. Redact secrets, tokens, credentials, private URLs, and sensitive personal data.
