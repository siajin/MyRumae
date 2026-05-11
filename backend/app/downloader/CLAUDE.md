# app/downloader — File Downloads + Dedupe

파일 1개 다운로드의 표준 시퀀스 (2단계 dedupe):

```
0) collector 단:
   - href 에서 filename_from_url(href) 추출
   - material_exists_by_filename(db, course_id, filename) 이면 click 자체를 스킵
1) 통과 시 사용자 click locator (page.expect_download)
2) suggested_filename → backend/data/temp/ 에 저장
3) SHA256 계산
4) sha_exists(sha) == True 면 temp 삭제 후 None 리턴 (DB upsert도 안 함)
5) 새 파일이면 Desktop/UOS_LMS_AI/<course>/<source_label>/원본/ 로 shutil.move
6) DownloadedFile(path, sha256, size_bytes, suggested_filename) 리턴
```

**파일명 dedupe (단계 0)** 는 네트워크 라운드트립을 줄이기 위한 fast-path. 정상 케이스(파일명 그대로 다시 올라온 경우)에 다운로드 자체를 안 한다. `pluginfile.php/.../filename.pdf` URL 패턴에서만 동작 — `view.php` 같은 서버 스크립트는 `filename_from_url` 이 None 을 돌려준다.

**SHA256 dedupe (단계 4)** 는 여전히 권위 있는 키. 같은 파일명으로 내용이 바뀐 재업로드는 이쪽에서 잡힌다 (Moodle 의 `pluginfile.php` URL 은 itemid 가 회전하므로 URL 기반 dedupe 는 절대 금지).

## 핵심 함수

[`download_via_click(page, locator, *, course_name, source_label, sha_exists, timeout_ms=60_000)`](download.py)

- `source_label`: 활동 이름 (`div.activityname` 의 text). dispatch 측이 채움. 빈 값이면 `paths.FALLBACK_SOURCE`("기타") 로 떨어진다.
- `sha_exists`: caller가 넘기는 `(sha) -> bool` 콜백. collector마다 `repo.material_exists_by_sha`를 lambda로 감싼다.
- 동시성 상한: 모듈 레벨 `_concurrency = asyncio.Semaphore(2)` — 너무 빠른 다운로드는 LMS가 차단할 수 있음. 늘리지 말 것.

## 경로 규약 ([paths.py](paths.py))

```
Desktop/UOS_LMS_AI/                    ← desktop_root()
└── <course_name>/                     ← sanitize_segment 적용
    └── <source_label>/                ← 활동 이름 (예: "강의자료실", "공지사항", "1주차 과제"). 빈 값이면 "기타"
        ├── 원본/                      ← 다운로드 파일
        └── 정리/                      ← docx_writer 가 쓰는 자료별 1개 DOCX
```

- **주차로 안 나눈다.** `Material.week` 컬럼은 메타데이터로만 남아 있고 경로 결정에 사용 안 함.
- **`sanitize_segment`**: Windows 금지문자(`<>:"/\\|?*` + 제어문자) → `_`. 끝의 `.`/공백 제거.
- **temp staging**: `backend/data/temp/`. 같은 이름 충돌 시 `1_<name>`, `2_<name>` 식으로 prefix.
- **shutil.move 사용**: temp(C:\\...\\backend\\data) → Desktop이 다른 볼륨일 수 있어 `Path.rename`은 위험.

## 변경 시 주의

- `desktop_root()`을 다른 위치로 옮기고 싶으면 [reset.py:reset_files](../../scripts/reset.py)도 같이 고쳐야 한다 (legacy `data/raw` 정리 분기 참고).
- temp 디렉토리는 `paths.ensure_dirs()`가 lazy 생성. 캐시/락파일 등 새로 두지 말 것 — `reset.py --files`가 `shutil.rmtree(temp)` 통째로 지움.
