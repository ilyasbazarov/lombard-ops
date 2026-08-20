# T-2-4 — шаг 13, приёмка без браузерного снимка (развилка Р-1, вариант А)

## Почему не снимок экрана

Редеплой (карточка 2, шаг 12) выполнен, ревизия `app-lombard-00003-p9d`, READY. В сессии найден
и исправлен дефект `T-2-1`: `static_url_path="/"` в `app/backend/main.py` регистрировал
собственный роут `/<path:filename>` раньше явного catch-all — `/login` и `/catalog` отдавали 404
на реальном сервисе. Исправлено (`static_folder=None`), `/catalog` теперь резолвится (200).

Экран `/catalog` после исправления рендерится пустым: консоль браузера — `FirebaseError:
auth/invalid-api-key`. Причина — известное, вне scope `T-2-4` ограничение `T-2-1`
(`07_STATE.md`): `gcloud run deploy --source` для Dockerfile-сборки не передаёт
`VITE_FIREBASE_*`, frontend-бандл собран без рабочего `firebaseConfig`. Донастройка —
отдельная задача.

## Пароль тестового пользователя

Прежний пароль `test-owner@lombard-ops.test` утерян владельцем (не хранится в репозитории,
`00 §4`). По подтверждению владельца сброшен новым значением через `accounts:update`
(Identity Toolkit REST, OAuth2-токен `gcloud auth print-access-token`, тот же механизм, что
`scripts/T-2-1_identity_platform_setup.sh users`) — `localId=yyY1TtEUs7c8RKgHXUWQ1aHupNb2`.
Само значение пароля в репозиторий, чат и логи не попадает.

## Проверка данных — эквивалент снимка

`accounts:signInWithPassword` → `idToken` → `GET /api/catalog` с `Authorization: Bearer <idToken>`
на реальном сервисе `https://app-lombard-450925595005.europe-west3.run.app`:

Ответ — 6 строк JSON, поля контракта `02 §2` + `price_source`/`updated_at`:

| make | model | liquidity_class | ltv_max | price_source |
|---|---|---|---|---|
| Toyota | Camry 70 | green | 0.75 | synthetic |
| Toyota | Prado | green | 0.70 | synthetic |
| Lexus | RX | green | 0.70 | synthetic |
| Mercedes-Benz | E | yellow | 0.55 | synthetic |
| Land Rover | Discovery | yellow | 0.50 | synthetic |
| Land Rover | Range Rover | red | null | synthetic |

Совпадает построчно с `bq query` (шаг 11, `reference/T-2-4_seed_and_load_2026-08-20.md`) и с
дефолтами `03 §3`. Все шесть строк `price_source=synthetic` — баннер синтетичности на реальных
данных экрана обязан быть виден (логика `Catalog.jsx`: `N = count(synthetic) > 0` → показан),
это подтверждено кодом компонента, не снимком: рендер самого экрана недостижим до фикса
`VITE_FIREBASE_*` (см. выше), это named-остаток задачи.
