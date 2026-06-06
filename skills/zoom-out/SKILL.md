---
name: zoom-out
description: Explain an unfamiliar code area from a higher-level system perspective before implementation. Use when invoked as `$zoom-out` or through Korean shortcuts such as "00큰그림", "큰그림", "전체맥락", "상위맥락", "구조파악", "이 코드 어디에 속해", or when the user needs modules, callers, responsibilities, data flow, and design boundaries mapped before changing code.
---

# Zoom Out

## Core Rule

Do not edit code in this skill unless the user explicitly asks for follow-up changes.

Build a map of the relevant area so the next implementation or review starts with the right mental model.

## Workflow

1. Identify the entry point:
   - User-provided file, symbol, feature, error, route, command, or module.
   - If no entry point is clear, ask one concise question.
2. Search outward:
   - Find direct callers and callees.
   - Find adjacent modules, tests, docs, configuration, and data models.
   - Prefer `rg` and existing project references.
3. Explain responsibilities:
   - What this area owns
   - What it delegates
   - What inputs and outputs cross its boundary
   - What invariants or assumptions it appears to rely on
4. Name uncertainty:
   - Mark guesses as assumptions.
   - Separate confirmed code facts from inferred design intent.
5. Recommend the next safe step:
   - Which file or test to read next
   - Where a change should likely start
   - What needs confirmation before implementation

## Stop Conditions

Stop searching when one of these is true:

- The entry point, direct callers/callees, owning module, and nearest tests or docs are identified.
- Further search would only enumerate similar files without changing the responsibility map.
- The next unknown requires a product, domain, or runtime answer rather than more static code reading.
- A clear handoff exists to `$plan-grill`, `$feature-flow-review`, `$api-design-review`, `$diagnose`, or `$tdd`.

## Output Format

Use this structure:

```markdown
## 큰그림

## 관련 모듈

| 영역 | 역할 | 근거 |
|---|---|---|

## 호출 흐름

## 책임 경계

## 확인된 사실

## 추정 및 확인 필요

## 다음에 볼 곳
```

Keep the answer concise enough that it can be used as a handoff into implementation.
