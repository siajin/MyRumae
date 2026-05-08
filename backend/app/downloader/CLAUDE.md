# app/downloader — File Downloads + Dedupe

파일 1개 다운로드의 표준 시퀀스:

```
1) 사용자 click locator (page.expect_download)
2) suggested_filename → backend/data/temp/ 에 저장
3) SHA256 계산
4) sha_exists(sha) == True 면 temp 삭제 후 None 리턴 (DB upsert도 안 함)
5) 새 파일이면 Desktop/UOS_LMS_AI/<course>/<N>주차/원본/ 로 shutil.move
6) DownloadedFile(path, sha256, size_bytes, suggested_filename) 리턴
```

## 핵심 함수

[`download_via_click(page, locator, *, course_name, week, sha_exists, timeout_ms=60_000)`](download.py)

- `sha_exists`: caller가 넘기는 `(sha) -> bool` 콜백. collector마다 `repo.material_exists_by_sha`를 lambda로 감싼다.
- 동시성 상한: 모듈 레벨 `_concurrency = asyncio.Semaphore(2)` — 너무 빠른 다운로드는 LMS가 차단할 수 있음. 늘리지 말 것.

## 경로 규약 ([paths.py](paths.py))

```
Desktop/UOS_LMS_AI/                    ← desktop_root()
└── <course_name>/                     ← sanitize_segment 적용
    └── <N>주차/  또는  기타/           ← week is None 이면 "기타"
        ├── 원본/                      ← 다운로드 파일
        └── 정리/                      ← docx_writer 가 쓰는 DOCX
```

- **`sanitize_segment`**: Windows 금지문자(`<>:"/\\|?*` + 제어문자) → `_`. 끝의 `.`/공백 제거.
- **temp staging**: `backend/data/temp/`. 같은 이름 충돌 시 `1_<name>`, `2_<name>` 식으로 prefix.
- **shutil.move 사용**: temp(C:\\...\\backend\\data) → Desktop이 다른 볼륨일 수 있어 `Path.rename`은 위험.

## 변경 시 주의

- `desktop_root()`을 다른 위치로 옮기고 싶으면 [reset.py:reset_files](../../scripts/reset.py)도 같이 고쳐야 한다 (legacy `data/raw` 정리 분기 참고).
- temp 디렉토리는 `paths.ensure_dirs()`가 lazy 생성. 캐시/락파일 등 새로 두지 말 것 — `reset.py --files`가 `shutil.rmtree(temp)` 통째로 지움.
