---
description: Run the login smoke test. Headed by default (for SSO/2FA pass-through); pass --headless to skip the window.
argument-hint: [--headless]
---

# /login — Login smoke + state.json refresh

UCLASS 로그인을 실행해서 `playwright-state/state.json`과 keyring을 채운다.

## 인자
- 기본: headed (창 띄움). 처음 로그인 / SSO 캡차 / 2FA 통과 / selector 검증용.
- `--headless`: 창 없이. 이미 한 번 통과한 후 점검용.

## 실행

```powershell
cd backend
# headed 기본
python scripts/smoke_login_headed.py

# --headless 인자 시
python scripts/smoke_login.py
```

## 출력 해석

```
[headed] state.json: 있음/없음, keyring: 있음/없음
is_logged_in: True
page.url: https://uclass.uos.ac.kr/my/
state path: ...\\backend\\playwright-state\\state.json
```

`is_logged_in: True` 가 나와야 끝. False 면:
1. SSO 가 학교 망 외부에서 막혔을 가능성 → VPN/도메인 PC 재확인
2. 비번 변경/만료 → keyring 자격증명 폐기 후 재입력 (`/reset` 후 재실행)
3. `LOGIN` 셀렉터 변경 → `selector-debugger` 호출

## 안전
- 비번을 채팅창에 입력하라고 요구하지 말 것 — 스크립트의 `getpass`가 직접 입력받음
- `state.json` 내용은 절대 출력하거나 사용자에게 보여주지 말 것
