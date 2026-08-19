# T-2-1 · Каркас app-lombard · шаги 1-3 (класс A) · 2026-08-19

## Стек и решение исполнителя (шаг 1)

- Backend: Python/Flask (`app/backend/`) — не Node/Express, вопреки первому побуждению читать
  «React + API» как «React + Node». `05_CONVENTIONS.md` строка 553 называет только каталог и
  общий стиль (Cloud Run приложение, React+API), язык API не мандатирован; конкретный стек по
  брифу — «на усмотрение исполнителя» (шаг 1). Python выбран для согласованности с остальным
  проектом (`connector/`, `functions/` — оба Python) и потому, что окружение сессии не имеет
  Node/npm (проверено: `node --version` → `command not found`), а Python и Flask уже установлены.
  Frontend — React (Vite), собирается на этапе Docker build (стадия `node:20-slim`), в сессии
  локально не установлен и не запускался — только код.
- Единый Cloud Run service: Flask отдаёт и `/api/*`, и статику собранного React (`app/Dockerfile`,
  multi-stage).

## Структура

```
app/
  backend/
    main.py            — Flask app, роуты /healthz, /api/whoami, /api/owner/only, статика
    auth.py            — require_auth (401), require_role (403), verify_id_token (точка подмены)
    requirements.txt   — Flask, firebase-admin, gunicorn
    tests/test_auth.py — шаг 2: локальные негативные сценарии
  frontend/
    src/pages/Login.jsx — экран /login (12_UX_CONTRACT.md §3.1)
    src/firebase.js      — конфиг Identity Platform Web SDK, значения из env на сборке (не хардкод)
    package.json, vite.config.js, index.html
  Dockerfile            — стадия 1 сборка React, стадия 2 Flask+gunicorn
```

## Шаг 2 — локальный тест негативных случаев (без деплоя, без сети)

`auth.verify_id_token` подменяется monkeypatch на фейковый decoded-токен — тест проверяет
middleware (401/403), не сеть/GCP (Identity Platform ещё не включена, шаг 4 не подтверждён).

Команда: `python3 -m pytest app/backend/tests/test_auth.py -v -s`

Результат (полный лог — `reference/T-2-1_pytest_log_2026-08-19.txt`, ниже — релевантные строки):

```
app/backend/tests/test_auth.py::test_no_token_returns_401 REQ: GET /api/whoami  (без заголовка Authorization)
RESP: 401 {'error': 'unauthorized', 'reason': 'missing_token'}
PASSED
app/backend/tests/test_auth.py::test_assessor_role_on_owner_resource_returns_403 REQ: GET /api/owner/only  (Authorization: Bearer <role=assessor>)
RESP: 403 {'error': 'forbidden', 'have': 'assessor', 'need': ['owner'], 'reason': 'role_mismatch'}
PASSED
app/backend/tests/test_auth.py::test_owner_role_on_owner_resource_returns_200 REQ: GET /api/owner/only  (Authorization: Bearer <role=owner>)
RESP: 200 {'ok': True, 'resource': 'owner-only'}
PASSED
app/backend/tests/test_auth.py::test_invalid_token_returns_401 REQ: GET /api/whoami  (Authorization: Bearer <garbage>)
RESP: 401 {'error': 'unauthorized', 'reason': 'invalid_token'}
PASSED
======================== 4 passed, 3 warnings in 0.21s =========================
```

4 из 4 тестов пройдены — вывод предъявлен логом (не кодом возврата). Покрывает часть критерия
приёмки «401 без токена» и «403 assessor→owner-ресурс» — ЛОКАЛЬНО. Задеплоенный сервис (шаг 8)
этой сессией не проверялся: деплой (шаг 6/7) — класс B, ждёт подтверждения владельца.

## Что НЕ сделано этой сессией (класс B, шаги 4-8 брифа)

- Шаг 4/5: включение Identity Platform, провайдер email+пароль, тестовые пользователи —
  не исполнено, ждёт карточки подтверждения.
- Шаг 6/7: деплой `app-lombard` на Cloud Run — не исполнено, ждёт карточки подтверждения.
- Шаг 8: приёмка на живом сервисе — недостижима без шагов 4-7.

## Расхождение T-2-0/T-2-0a (названо, не устранено — вне scope этого брифа)

Стенд-ап `07_STATE.md` называет `T-2-0` «done» дважды (строки «Прошлый шаг», «Следующий шаг»), но
в `04_ROADMAP.md` `T-2-0` несёт статус `todo` и брифа `T-2-0.md` нет. Готова и закрыта другая,
похоже названная задача — `T-2-0a` (`12_UX_CONTRACT.md`, done). На допуск `T-2-1` это не влияет:
зависимость `T-2-1` — `T-1-0`, не `T-2-0`. Правка `07_STATE.md` — не шаг этого брифа (`ADR-028`).
