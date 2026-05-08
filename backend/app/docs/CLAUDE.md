# app/docs — DOCX Summary Generator

사용자 노출 산출물은 **모두 DOCX**. 마크다운은 내부 저장(`Summary.summary_md`)만 — 사용자에게 직접 보여주지 않는다.

## 단일 진입점

[`generate_course_summaries(db, *, course)`](docx_writer.py) — 강좌의 모든 주차에 대해 `<N>주차_강의정리.docx`를 `Desktop/UOS_LMS_AI/<course>/<N>주차/정리/`에 쓴다.

호출 사이트:
- `scheduler.full_sync` 가 강좌별로 매 sync 후 호출
- `scripts/smoke_docs.py` 가 LMS 접속 없이 DB만으로 재생성

## DOCX 구조 (변경 시 모든 주차에 반영됨)

```
제목:    <과목> — <N>주차 강의 정리
메타:    과목 / 강좌 코드 / 교수 / 학기 / 주차 / 생성일
H1:      수집 자료      ← Material 행 bullet (file_type 태그 포함)
H1:      핵심 개념      ← Summary.summary_md 가 있으면 라인별 출력
H1:      중요 내용      ← 빈 bullet 3개 (사용자가 수기 작성)
H1:      시험 포인트    ← 빈 bullet 2개
H1:      복습 체크리스트 ← Material마다 ☐ 2줄
```

빈 bullet은 사용자가 학습 후 채우는 영역. 자동 채우기 금지.

## 한글 폰트

```python
_set_korean_default_font(doc)  # 맑은 고딕, 11pt
```

새 paragraph/heading 추가 시 별도 폰트 지정하지 말 것 — Normal 스타일이 상속된다.

## 주차 정렬

`_distinct_weeks`는 `(week is None, week)` 튜플로 정렬. 결과: `1주차, 2주차, ..., 기타` 순.

## AI 요약 통합 지점

향후 ollama 등으로 생성한 요약은 `Summary.summary_md`에 upsert (`repo.upsert_summary`). DOCX 재생성 시 자동으로 "핵심 개념" 섹션에 채워진다 — DOCX 코드는 건드릴 필요 없음.
