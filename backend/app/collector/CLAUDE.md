# app/collector — UCLASS Scrapers

Playwright 비동기 API 기반 스크레이퍼들. 각 파일은 한 종류의 LMS 자원만 책임진다.

| 파일 | 책임 |
|---|---|
| `browser.py` | `async_playwright` 컨텍스트 매니저 (`storage_state` 자동 로드) |
| `courses.py` | `/my/` 사이드바에서 수강 강좌 목록 추출 |
| `course_page.py` | 강좌 페이지의 활동 스냅샷 → modtype별 디스패치 |
| `folders.py` | `modtype_folder` 자료실(다파일)의 첨부 다운로드 |
| `ubboard.py` | `modtype_ubboard` 공지/게시판 글 + 첨부 |
| `ubfile.py` | `modtype_ubfile` 단일 파일 활동 — 자동 다운로드 또는 pluginfile 링크 클릭 |
| `assignments.py` | `modtype_assign` 과제 메타 + 첨부 |

## 절대 깨면 안 되는 패턴

### 1. 셀렉터는 [selectors.py](../selectors.py)에서만

```python
# OK
from ..selectors import COURSE
await page.goto(COURSE.URL_FLAT.format(cid=cid), ...)

# 금지 — 인라인 셀렉터
await page.locator("li.section[id^='section-']").all()
```

UCLASS UI 변경은 `selectors.py` 한 파일 수정으로 끝나야 한다.

### 2. Locator를 navigate 전반에 걸쳐 보관 금지

활동 목록은 `_snapshot_activities`처럼 **`page.evaluate`로 dict 배열을 한 번에 떠서** dataclass(`ActivityRef`)로 가지고 다닌다. 활동 페이지로 이동하면 이전 페이지의 Locator는 모두 stale.

### 3. 한 활동의 실패가 전체 sync를 죽이지 않게

```python
for ref in refs:
    try:
        ...
    except Exception:
        log.exception("activity cmid=%s failed", ref.cmid)
        counts["skipped"] += 1
```

[course_page.collect_course_materials](course_page.py)의 try/except 블록 형태를 유지.

### 4. URL은 `URL_TMPL.format(cmid=...)`

cmid/course id 직접 조립 금지. 모든 LMS URL은 `selectors.py`의 템플릿을 통과해야 함.

## 새 modtype 추가 절차

1. [selectors.py](../selectors.py)에 셀렉터 클래스 추가, `KNOWN_MODTYPES` 튜플에 modtype 이름 추가
2. `app/collector/<modtype>.py` 생성 — `collect_<modtype>(page, *, db, course_id, course_name, cmid, week=None, source_label=None) -> int` 시그니처 유지. **`source_label`은 dispatch 측이 활동 이름으로 채워주므로 반드시 내부 `download_via_click(..., source_label=source_label)` 와 `repo.insert_material(..., source_label=source_label)` 두 군데에 전달할 것** — 빠뜨리면 첨부가 전부 "기타" 폴더로 떨어진다. `week`는 dispatch 측이 section_idx 로 채우지만 메타데이터 용도일 뿐(경로 결정에는 사용 안 함).
3. [course_page.collect_course_materials](course_page.py)의 dispatch에 `elif ref.modtype == "..."` 분기 추가. `_source_label_for(ref)` 로 활동 이름을 얻는다.
4. 필요하면 [db/models.py](../db/models.py)에 새 테이블 + [repository.py](../db/repository.py)에 upsert 함수 (테이블에 `source_label` 컬럼도 같이 추가하면 DOCX 그룹화가 자동 정렬됨)
5. `scripts/smoke_collect.py` 로 검증

## 데이터 추출 표준

- 텍스트: `_safe_inner_text(page, selector)` 패턴 — 없으면 `None` 반환, 예외 삼킴
- HTML: `_safe_inner_html` (공지 본문 등 원문 보존이 필요한 경우)
- 날짜: 파일별 `_DATE_RE` 정규식 — 한국어/영문 모두 받기. 마감일 파싱은 `assignments._parse_due` 참고
