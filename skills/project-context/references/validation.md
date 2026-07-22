# 검증

## 성공 기준

```bash
python3 -B <skill-dir>/scripts/validate_project_context.py .
```

exit 0만 완료다. warning은 보고하지만 완료를 막지 않는다. error를 warning으로 낮추거나 metadata를 수동 편집해 우회하지 않는다.

## 오류 검사

- managed path와 parent가 symlink가 아님
- `_plan.md` 없음
- 홈과 metadata 존재
- schema v2, current generator version
- 홈과 metadata의 canonical full `source_commit`, metadata `reviewed_commit`과 올바른 ancestry
- 홈 `updated_at`의 UTC millisecond 형식
- 홈 frontmatter source와 metadata source 일치
- 홈→area index→concept 최대 2단계
- 빈 area index와 평면/deep concept 없음
- concept `type`, `title`, `description`, `read_when` 완전
- concept title이 전체 wiki에서 대소문자 무시 기준으로 유일함
- area index `generated_by`, `title`, `description`, `read_when` 완전
- generated index marker와 metadata 기반 렌더링 일치
- 홈 mode와 실제 page 구조 일치
- 홈 body 4,000자 이하
- 홈·concept에 `## 근거`와 실제 source link 존재
- repo 밖 링크, absolute host path, broken internal link 없음
- private key, access key, secret-looking assignment 없음
- metadata `pages`, `indexes`, `doc_sources`, `doc_hashes`, `content_hash`가 현재 tree와 일치
- unmapped resolution 구조와 reason 유효
- top-level agent marker가 하나이며 current

## 경고

- 근거와 판단 정보가 부족한 얇은 concept
- 다른 concept와 의미 관계가 없는 semantic orphan
- persistent commit hash 목록 의심
- 홈 권장 section 누락

semantic orphan warning은 링크 수를 강제하지 않는다. 링크만 있는 목록은 관계로 세지 않는다. 독립 page가 의도적이면 warning을 완료 보고에 남긴다.

## 최종 확정 실패 처리

candidate validation 실패 시 metadata와 plan은 그대로 남는다. 문제를 수정하고 같은 snapshot 기준으로 finalize를 다시 실행한다.

최종 on-disk validation 실패 시 helper가 이전 metadata와 삭제한 plan을 복구한다. generated index는 이미 source metadata로 결정적으로 재생성된 파일이므로 남을 수 있다. index 문제를 수정한 뒤 다시 finalize한다.

## 안전 경계 검증

helper는 고정 경로만 쓴다.

- `docs/project-context.md`
- `docs/project-context/`
- `docs/project-context/.metadata.json`
- `docs/project-context/_plan.md`
- top-level agent marker

CLI의 `--doc`, `--metadata`, `--plan-path` 같은 managed path override는 지원하지 않는다. repo root는 실제 Git top-level과 같아야 한다. destination collision, non-regular file, symlink tree는 write 전에 실패해야 한다.
