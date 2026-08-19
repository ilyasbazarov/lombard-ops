# T-2-1 · Деплой Cloud Run и приёмка на живом сервисе — лог (2026-08-19)

Карточка подтверждения 2 (шаг 6/7 брифа `T-2-1`) подтверждена владельцем в чате 2026-08-19,
исполнена в этой сессии.

## Шаг 6→7 — деплой

Команда: `bash scripts/T-2-1_deploy.sh deploy`

- Билд-аккаунт проверен перед подстановкой: `gcloud iam service-accounts describe
  lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com` → непустой `uniqueId:
  115827718002622110291`.
- `gcloud run deploy app-lombard --source=app --region=europe-west3
  --service-account=lombard-pipeline@... --build-service-account=.../lombard-build@...
  --allow-unauthenticated` — билд и деплой из чистой папки `app/`.
- `gcloud run services describe app-lombard --region=europe-west3`:
  ```
  URL:     https://app-lombard-450925595005.europe-west3.run.app
  Traffic: 100% LATEST (app-lombard-00001-v7d)
  Service account: lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
  ```
  Сервис отдаёт трафик (READY эквивалент — 100% LATEST + `Done.` в выводе деплоя), регион и URL
  подтверждены командой, не предполагаются.

**Известное ограничение, не блокирует приёмку T-2-1:** `gcloud run deploy --source` для
Dockerfile-сборки не поддерживает передачу `VITE_FIREBASE_*` как Docker `ARG` (только
`--set-build-env-vars`, применимо к buildpacks, не к явному `Dockerfile`) — frontend-бандл
`/login` собран без `firebaseConfig`. Критерии приёмки T-2-1 это не задевает: логи ниже получены
прямым вызовом Identity Toolkit REST (`accounts:signInWithPassword`) и backend API, как это
делает любой клиент, включая будущий фикс frontend-сборки. Донастройка frontend build-args —
предмет заведения новой задачи (метка `метод`, не `продукт`), не этой сессии `T-2-1`.

## Шаг 8 — приёмка на живом сервисе

Сервис: `https://app-lombard-450925595005.europe-west3.run.app`

**(а) вход test-owner по паролю → ответ с токеном:**
```
POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=<apiKey>
{"email":"test-owner@lombard-ops.test","password":"<пароль владельца>","returnSecureToken":true}
→ localId: yyY1TtEUs7c8RKgHXUWQ1aHupNb2, email: test-owner@lombard-ops.test, idToken присутствует (1004 симв.)
```

**(б) запрос без токена → 401:**
```
GET /api/owner/only (без Authorization)
→ HTTP 401 {"error":"unauthorized","reason":"missing_token"}
```

**(в) test-assessor → ресурс роли owner → 403:**
```
GET /api/owner/only  Authorization: Bearer <idToken test-assessor>
→ HTTP 403 {"error":"forbidden","have":"assessor","need":["owner"],"reason":"role_mismatch"}
```

**Sanity (вне обязательных критериев):** test-owner → `/api/owner/only` → `HTTP 200
{"ok":true,"resource":"owner-only"}` — подтверждает, что 403 выше — следствие роли, а не общая
поломка эндпоинта.

Токены целиком в лог/чат не выводились (секрет сессии), только факт присутствия и длина.
