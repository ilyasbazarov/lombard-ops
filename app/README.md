# app-lombard

Cloud Run приложение `app-lombard` (бриф `T-2-1`): Flask API (`backend/`) + React frontend
(`frontend/`), единый образ (`Dockerfile`), за Identity Platform (email+пароль, custom claims
`owner`/`manager`/`assessor`).

- `backend/main.py`, `backend/auth.py` — API, 401 без токена, 403 при несовпадении роли.
- `backend/tests/test_auth.py` — локальные негативные сценарии (без деплоя, без сети).
- `frontend/src/pages/Login.jsx` — экран `/login` (`12_UX_CONTRACT.md §3.1`).
- Деплой (Identity Platform, Cloud Run) — класс B, `scripts/T-2-1_identity_platform_setup.sh`,
  `scripts/T-2-1_deploy.sh`, только после подтверждения владельца.

Экраны реестра/карточки/справочника/осмотра (`T-2-2`…`T-2-5`) — вне scope `T-2-1`.

Детали и лог теста — `reference/T-2-1_backend_frontend_skeleton_2026-08-19.md`.
