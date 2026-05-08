---
description: Verify selectors in backend/app/selectors.py against the saved HTML samples at the repo root. Surface drift before it breaks production.
---

# /selector-check — 셀렉터 vs 저장된 HTML 샘플 대조

UCLASS UI 가 바뀌었을 가능성을 빠르게 확인. 실제 LMS에 접속하지 않고 리포 루트의 4개 HTML 파일만 사용.

## 검증 대상

| 셀렉터 그룹 | 검증 HTML |
|---|---|
| `LOGIN.*` | `사이트에 로그인 _ 서울시립대학교 온라인강의실.html` |
| `HOME.*` | `홈 _ 서울시립대학교 온라인강의실.html` |
| `COURSE.*` | `강좌_ C프로그래밍 _ 서울시립대학교 온라인강의실.html` |
| `BOARD.ARTICLE_LINK` | `C프로그래밍 (2026-10, 40121_01_U) _ 공지사항 _ 서울시립대학교 온라인강의실.html` |

미검증 (샘플 없음, 추측 상태):
- `BOARD.ARTICLE_TITLE / AUTHOR / POSTED_AT / BODY` (게시글 본문 페이지)
- `ASSIGN.DUE_AT_ROW_LABEL / VALUE / DESCRIPTION` (과제 페이지)
- `FOLDER.DOWNLOAD_FOLDER_BTN` (폴더 zip 다운로드)
이 그룹은 본 커맨드로 검증 불가 — `/login` 후 headed 브라우저로 직접 확인.

## 절차

1. [backend/app/selectors.py](../../backend/app/selectors.py) 의 각 셀렉터 문자열 추출
2. 위 표의 매핑된 HTML 파일을 Grep — 매칭 0건이면 깨진 셀렉터 후보
3. 후보별로 다음을 보고:
   ```
   CLASS.FIELD: "<현재 셀렉터>"
     매칭 수: 0
     HTML 라인 N: <비슷한 마크업>
     제안: "<새 셀렉터>"
   ```
4. 변경 제안은 `selector-debugger` 에이전트로 넘기거나 사용자에게 직접 적용 동의 받기

## 하지 말 것
- 코드를 자동 패치 (제안만)
- 검증 안 된 그룹(공지 본문 등)을 "OK" 로 보고 — 미검증 상태로 명시
