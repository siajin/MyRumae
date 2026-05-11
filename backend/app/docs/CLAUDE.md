# app/docs — DOCX Summary Generator

사용자 노출 산출물은 **모두 DOCX**. 마크다운은 내부 저장(`Summary.summary_md`)만 — 사용자에게 직접 보여주지 않는다.

## 산출물 규칙 (post-refactor)

- **자료 1개당 DOCX 1개.** PDF/PPT/DOCX 하나마다 `<파일명>_정리.docx` 1개를 만든다.
- **공지/과제도 별도 DOCX.** 게시판 글 1개당, 과제 1개당 각각 DOCX를 만든다 (본문/설명 + 첨부 본문).
- **그룹화는 활동 이름(source_label) 기준.** 더 이상 주차 폴더로 안 나눈다.

```
Desktop/UOS_LMS_AI/<course>/
└── <source_label>/                    ← 활동 이름. "강의자료실"/"공지사항"/"1주차 과제" 등
    ├── 원본/                          ← downloader 가 떨군 파일
    └── 정리/
        ├── <파일명>_정리.docx          ← Material 1행당 1개
        ├── 공지_<글제목>.docx          ← Notice 1행당 1개
        └── 과제_<과제명>.docx          ← Assignment 1행당 1개 (첨부 본문 동봉)
```

## 진입점

- [`generate_material_docx(db, *, course, material)`](docx_writer.py) — 파일 1개 → DOCX 1개
- [`generate_notice_docx(db, *, course, notice)`](docx_writer.py) — 공지/게시판 글 1개 → DOCX 1개
- [`generate_assignment_docx(db, *, course, assignment)`](docx_writer.py) — 과제 1개 → DOCX 1개 (첨부 본문 포함)
- [`generate_course_summaries(db, *, course)`](docx_writer.py) — 위 3개를 강좌 단위로 일괄 실행
- [`generate_all(db)`](docx_writer.py) — 전 강좌

호출 사이트:
- `scheduler.full_sync` 가 강좌별로 매 sync 후 `generate_course_summaries` 호출
- `app.cli regen-docx` (구 `scripts/smoke_docs.py`) 가 LMS 접속 없이 DB만으로 재생성

## DOCX 구조

```
공통 헤더:  과목 / 강좌 코드 / 교수 / 학기 / 출처(=source_label) / 생성일
(Material)  파일 / 형식 / [주차 + 주제(주차가 syllabus 에 있을 때만)]
            H1 "파싱 본문" — ParsedContent 블록 (페이지 헤더 + 본문 텍스트)
(Notice)    작성자 / 게시일 / 원문 URL
            H1 "본문" — body_html → 텍스트화
(Assignment) 마감 / 제출 상태 / 원문 URL
             H1 "과제 설명" — description_html → 텍스트화
             H1 "첨부 파일 본문" — 이 과제 cmid 로 묶인 Material 의 ParsedContent
```

AI 요약 (구 "핵심 개념" 등 빈 bullet 섹션) 은 ai-purring-goose 리팩토링에서 제거됨.

## 한글 폰트

```python
_set_korean_default_font(doc)  # 맑은 고딕, 11pt
```

새 paragraph/heading 추가 시 별도 폰트 지정하지 말 것 — Normal 스타일이 상속된다.

## 파일명 안전화

`_safe_filename` → `paths.sanitize_segment` + 80자 제한. Notice/Assignment 제목이 너무 길거나 금지문자 포함이어도 안전.

## AI 요약 통합 (현재 비활성, 코드만 보존)

`Summary` 모델 / `repo.upsert_summary` 는 향후 LLM 요약 부활용으로 남겨둠. 현재 docx_writer 는 이 테이블을 **읽지 않는다.** 부활 시: `_write_parsed_body` 인근에 별도 H1 ("AI 요약") 섹션을 추가하는 방향이 자연스러움 — 기존 "파싱 본문" 을 덮지 않게.
