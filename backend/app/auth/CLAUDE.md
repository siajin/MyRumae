# app/auth — Login Subsystem

UCLASS는 **모든 페이지 접근 전 SSO 검증**이 필요하다. 이 모듈의 단 하나의 외부 진입점은 `login.ensure_logged_in(context, page, *, allow_manual, prompt_credentials)`.

## 우선순위 (절대 바꾸지 말 것)

```
1) state.json (Playwright storage_state)
        ↓ 실패
2) keyring 자격증명 → /login 폼 자동 입력
        ↓ 실패  &&  allow_manual=True
3) prompt_credentials() 콜백 → 입력 → keyring 저장 → 폼 입력
```

스케줄러 잡(`full_sync`)은 **반드시 `allow_manual_login=False`** — 백그라운드 실행 중 input prompt가 뜨면 안 되기 때문.

## 함정

- **로그인 페이지 진입 자체가 SSO 리디렉트로 끊길 수 있음.** `_login_with_credentials`는 `page.goto`에서 `Exception`을 잡아 `info` 로그만 남기고 통과시킨다. 이건 버그가 아니라 정상 흐름.
- **SSO 통과 후 url 검사로는 부족.** `is_logged_in()`은 `/my/`로 한 번 더 navigate 하고 `HOME.LOGOUT_LINK` 존재 여부로 판단한다.
- **수동 입력 도중에 SSO가 살아날 수 있음.** prompt 후 폼 채우기 전에 `is_logged_in` 한 번 더 체크 — 빠뜨리지 말 것.

## 보안 원칙

- 비밀번호는 `keyring.set_password(SERVICE="uclass-lms", username, password)` 로만 보관
- `_username_` 키에 활성 사용자명을 마커로 저장 (단일 사용자 가정)
- 로그에 비밀번호/세션 토큰 출력 금지 — 사용자명까지가 한계
- `state.json`은 gitignored — 커밋하면 즉시 재발급 (UCLASS 비번 변경)

## 변경 시 점검

`scripts/smoke_login.py`(headless), `scripts/smoke_login_headed.py`(headed) 둘 다 통과해야 한다. headed가 통과하지 못하면 SSO 흐름이 변경된 것 — `LOGIN`/`HOME` 셀렉터 또는 페이지 url 패턴을 다시 살펴라.
