---
name: feature-flow-review
description: Use when a user asks to review, design, or document a new feature flow before API design or implementation, including Korean shortcuts such as "기능플로우리뷰", "플로우리뷰", "기능 흐름 정리", or "플로우 문서 작성". Use especially for multi-step features with user branching, state transitions, permissions, tokens, approval, signup, authentication, payment, settlement, account linking, or external integrations.
---

# Feature Flow Review

## When To Use

Use this skill before API detail design or implementation when the request involves:

- Multi-step features
- User types or branch conditions
- State transitions, roles, permissions, or approval
- Tokens, temporary storage, or external integrations
- Multiple APIs whose overall flow is not confirmed yet

Do not use this skill for simple CRUD, minor field additions, copy changes, or clearly bounded implementation fixes.

## Core Rule

Do not finalize API endpoints, DTOs, entities, or implementation in this skill.

Always stop before API detail design. API detail review belongs to a separate skill.

If unresolved flow, state, token, or branch decisions remain, say:

```text
플로우를 먼저 확정한 뒤 API 상세로 넘어가겠습니다.
```

## Workflow

1. Summarize the feature scope:
   - Purpose
   - Target users
   - Entry condition
   - Completion condition
   - External integrations
2. Define user types and branch criteria.
3. Draft the overall user flow before listing APIs.
4. Draft state transitions.
5. Draft token, temporary storage, and external integration model.
6. Check consistency with existing code and user-provided external responses when context is available.
7. List design-impacting edge cases by priority:
   - Blocker
   - Important
   - Reference
8. Stop before API detail design.

## Output Format

Respond in this order:

1. 기능 요약
2. 사용자 유형 및 분기 기준
3. 전체 플로우 초안
4. 상태 전이 초안
5. 토큰/임시 저장 초안
6. 기존 코드/외부 응답 정합성 체크
7. 확인 필요한 핵심 엣지케이스
8. 다음 단계

For the final section:

- If blockers remain, say `플로우를 먼저 확정한 뒤 API 상세로 넘어가겠습니다.`
- If no blockers remain, say `플로우를 기준으로 다음 단계는 별도 API 상세 리뷰입니다.`

Use Mermaid when useful:

- `flowchart TD` for user flow
- `stateDiagram-v2` for state transitions

## Document Mode

If the user asks to create a flow document, write the result to a Markdown file.

Use document mode when the user says things like:

- `문서까지`
- `문서 작성`
- `flow 문서`
- `플로우 문서`
- `저장해줘`
- `경로: <path>`
- `파일: <path>`
- `저장 위치: <path>`

### Path Policy

Do not assume a project-specific docs directory.

Determine the output path in this order:

1. If the user provides an explicit file path, use it.
2. If the user provides a directory, create `<feature>_flow.md` inside it.
3. If the repository has an obvious feature/spec docs pattern, propose that path but do not create the file until the user confirms it.
4. If no path is clear, ask the user where to save the document.

Recognize Korean path hints such as `경로:`, `파일:`, and `저장 위치:` as explicit path input.

Default filename:

```text
<feature>_flow.md
```

Use lowercase snake_case for `<feature>` unless the project already uses another naming convention.

### Update Policy

If the target file already exists:

- Read it first.
- Preserve confirmed decisions.
- Update only sections affected by the new request.
- Move resolved questions out of unresolved items.
- Do not overwrite unrelated content.

### Recommended Sections

Include sections that are relevant to the feature:

- 배경 및 목적
- 용어 정의
- 사용자 유형 및 분기 기준
- 전체 플로우
- 분기별 상세 플로우
- 상태 전이 표
- 토큰/임시 저장 모델
- 기존 코드/외부 응답 정합성 체크
- 외부 연동 지점
- 엣지케이스 및 미확정 사항
- Mermaid 다이어그램 when useful

## Handoff Policy

After creating or updating the flow document:

- Stop before API detail review.
- If the user also asked for `API리뷰까지`, `api spec까지`, or `다음 단계까지`, finish the flow review first, then explicitly ask for confirmation before starting `$api-design-review`.
- If blockers remain, say:

```text
플로우를 먼저 확정한 뒤 API 상세로 넘어가겠습니다.
```

- If no blockers remain, say:

```text
플로우 문서를 기준으로 다음 단계는 별도 API 상세 리뷰입니다.
```

## Solution Capture Follow-up

If the review produced a reusable domain decision, state transition rule, token/storage policy, external integration pattern, or approval/payment/settlement flow convention, suggest `$solution-capture` in one sentence.

Do not create a solution note unless the user confirms.
