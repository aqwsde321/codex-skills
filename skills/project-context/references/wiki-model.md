# Wiki model

## 문서 트리

```text
docs/project-context.md
docs/project-context/
├── <area>/
│   ├── index.md
│   └── <concept>.md
└── .metadata.json
```

`_plan.md`는 write run 중에만 존재하는 임시 파일이다. 홈, 모든 `index.md`, `_plan.md`를 제외한 Markdown 문서는 concept page다. concept를 세 단계 이상 중첩하거나 `docs/project-context/` 바로 아래에 평면 page를 두지 않는다.

area 이름은 architecture, workflow, domain 같은 고정 enum이 아니다. 저장소의 실제 소유권과 탐색 경계를 따른다. concept가 없는 area와 index는 만들지 않는다.

초기 생성은 concept 최대 12개를 soft cap으로 삼고 최소 개수는 강제하지 않는다. 이후 실제 개념이 생길 때 확장한다. page 수 자체보다 중복, semantic orphan, 근거 없는 얇은 page를 경계한다.

## 홈

`docs/project-context.md`는 router다. 프로젝트 개요, 전역 변경 주의점, 선택적 `## 문서화 백로그`, 최소 source 근거를 둔다. concept가 있는 multi-page wiki에서만 helper가 generated `## Context Index`를 둔다. body는 4,000자 이하로 유지한다.

```yaml
---
generated_by: project-context
source_commit: <canonical full Git object id>
updated_at: <ISO-8601 UTC>
mode: single-page|multi-page
---
```

concept가 없으면 `single-page`, 하나 이상이면 `multi-page`다. home-only도 schema v2로 기록한다.

## Area index

area index의 설명 frontmatter와 marker 바깥 소개 문장은 사람이 관리할 수 있다. marker 내부 목록은 helper만 관리한다.

```yaml
---
title: 결제
description: 결제 영역의 프로젝트 컨텍스트
read_when: 결제 관련 코드를 조사하거나 변경할 때
generated_by: project-context-index
---
```

```md
<!-- project-context:index:start -->
<!-- project-context:index:end -->
```

`sync-index`는 새 concept의 area index를 생성하고, 홈에는 area index만, area index에는 바로 아래 concept만 연결한다. 빈 index는 자동 삭제하지 않고 error로 보고한다.

## Concept page

```yaml
---
type: workflow
title: 주문 취소 흐름
description: 취소 조건과 환불·재고 복원 과정
read_when: 주문 취소 API나 환불 상태를 변경할 때
tags: [orders, refund]
---
```

`type`은 저장소에 맞는 자유로운 짧은 값이다. `title` 80자, `description`과 `read_when`은 각각 160자 이하 plain text다. `tags`는 선택이다.

본문 heading은 고정하지 않는다. 개념의 목적, 흐름과 규칙, 변경 위험, 검증 방법, 관련 개념을 필요한 만큼 쓴다. `## 근거`와 repo-relative source link는 필수다.

## 의미 링크

관계를 설명하는 문장 안에서 concept를 연결한다.

```md
[환불 흐름](../payments/refund.md)은 주문 취소 승인 뒤 시작되며,
결제사 응답에 따라 보상 처리 상태가 달라진다.
```

semantic graph는 concept 본문 링크만 사용한다. 홈·area index navigation, generated marker, `## 근거` source link는 제외한다. incoming과 outgoing 이웃을 모두 1-hop 검토 후보로 사용한다. 후보는 읽고 영향 여부를 판단할 대상이지 자동 수정 대상이 아니다.

## Metadata schema v2

`.metadata.json`의 핵심 필드:

- `generator`, `generator_version`, `schema_version`
- `updated_at`, `run_mode`
- `source_commit`, `source_commit_short`, `reviewed_commit`
- `primary_doc`, `pages`, `indexes`
- `doc_sources`, `doc_hashes`, `content_hash`
- `unmapped_resolutions`

`pages`는 홈과 concept, `indexes`는 area index다. `doc_sources`와 `doc_hashes` key는 `pages`와 정확히 같아야 한다. `source_commit`과 `reviewed_commit`은 mutable ref나 short SHA가 아닌 canonical full object ID다.
