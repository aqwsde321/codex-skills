---
name: simplification-debt
description: Collect intentional simplification debt markers from a repository by scanning `ponytail:` comments and reporting each shortcut's known ceiling and revisit trigger. Use when invoked as `$simplification-debt` or through Korean shortcuts such as "단순화부채", "부채리뷰", "단순화 부채", "ponytail-debt", or when the user asks to list deferred simplifications, ponytail comments, or simplification debt.
---

# Simplification Debt

## Core Rule

Report deliberate simplification markers; do not edit code by default.

A marker must be a source-code comment containing `ponytail:`. Plain prose that mentions `ponytail:` without a comment prefix is not debt.

Expected convention:

```text
// ponytail: <known ceiling>, <revisit trigger or upgrade path>
# ponytail: <known ceiling>, <revisit trigger or upgrade path>
```

## Workflow

1. Run `scripts/collect_simplification_debt.py` from this skill against the repository root.
2. Review each marker for two parts:
   - the simplification ceiling or limitation
   - the trigger or upgrade path that says when to revisit it
3. Flag any marker without a trigger as `no-trigger`.
4. Report grouped results by file and line.
5. If the user asks to persist the ledger, write it to the requested path. If no path is given, use `SIMPLIFICATION-DEBT.md`.

## Script

Use:

```bash
python3 <skill-dir>/scripts/collect_simplification_debt.py [repo-root]
```

If `repo-root` is omitted, the script scans the current working directory.

The script skips common dependency and build directories such as `.git`, `node_modules`, `dist`, `build`, `target`, `.next`, and `coverage`.

## Output

If markers exist, report:

```text
path/to/file.ext:
  L42: global lock
    trigger: switch to per-account locks when lock wait time appears in profiling

N markers, M with no trigger.
```

If no markers exist, report:

```text
No ponytail: debt. Clean ledger.
```

## Boundaries

- Do not treat every TODO as simplification debt.
- Do not modify or delete `ponytail:` comments unless the user explicitly asks.
- Do not count markers inside `.git`, dependency directories, build output, or generated artifacts.
- If a marker is stale because the code no longer has that simplification, report it as a cleanup candidate instead of silently ignoring it.
