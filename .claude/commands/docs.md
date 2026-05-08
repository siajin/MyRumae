---
description: Regenerate DOCX summaries from the local DB (no LMS access). Optionally limit to one course.
argument-hint: [course-db-id]
---

# /docs — DOCX 정리노트 재생성

LMS 에 접속하지 않고 `lms.db` 에 이미 들어 있는 데이터로 `Desktop/UOS_LMS_AI/.../정리/<N주차>_강의정리.docx` 를 다시 쓴다.

언제 쓰나:
- DOCX 템플릿(`docx_writer.py`) 변경 후 모든 주차 재반영
- AI 요약(`Summary.summary_md`) 새로 생성한 후 "핵심 개념" 섹션 갱신
- 기존 DOCX가 손상돼서 재생성

## 실행

```powershell
cd backend
# 전체
python scripts/smoke_docs.py

# 한 강좌만 (DB id, course.moodle_course_id 아님)
python scripts/smoke_docs.py --course $ARG_COURSE_ID
```

## 출력 해석

```
과목: <name>
생성된 DOCX: <N>개
  - C:\\Users\\...\\Desktop\\UOS_LMS_AI\\<강좌>\\<N>주차\\정리\\<N>주차_강의정리.docx
```

- 0 개로 나오면 그 강좌에 `Material` 행이 없다는 뜻 → `/smoke-collect <idx>` 를 먼저 돌려야 함
- DOCX 가 안 열리면 `docx-tuner` 에이전트로 템플릿 점검

## 사이드 이펙트
- 같은 경로에 기존 DOCX 가 있으면 덮어쓴다. 사용자가 수기로 채운 "중요 내용"/"시험 포인트" 영역도 덮인다 — 사용자에게 경고 후 실행.
