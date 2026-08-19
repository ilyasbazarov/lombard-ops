# T-2-1 · Identity Platform setup — лог (2026-08-19)

Карточка подтверждения 1 (шаг 4/5 брифа `T-2-1`) подтверждена владельцем в чате 2026-08-19,
исполнена в этой сессии.

## Дефект метода, исправлен в этой же сессии

`scripts/T-2-1_identity_platform_setup.sh` изначально использовал `gcloud alpha identity
platform config update` и `firebase-admin` (Python) с Application Default Credentials — оба
пути недоступны в среде исполнения:

- `gcloud alpha identity platform …` — такой группы команд нет в установленном SDK 577.0.0
  (проверено `gcloud alpha identity --help`, есть только `groups`).
- Продукт Identity Platform требует однократной ручной активации в Cloud Console
  (`console.cloud.google.com/customer-identity`) — до неё `admin/v2/.../config` отдаёт
  `404 CONFIGURATION_NOT_FOUND` даже после `gcloud services enable identitytoolkit.googleapis.com`.
  Активация выполнена владельцем вручную в браузере (подтверждено в чате: «Successfully enabled
  Identity Platform»).
- `firebase-admin` требует `gcloud auth application-default login` (интерактивный браузерный
  логин) — недоступно в этой среде.

Оба места заменены на прямой REST-вызов `identitytoolkit.googleapis.com` с OAuth2-токеном
`gcloud auth print-access-token` (тот же токен, что использует `gcloud`, scope
`cloud-platform` уже выдан интерактивным логином `ilyasbazarov4@gmail.com`). Текст исправления —
в самом скрипте (комментарии «ИСПРАВЛЕНО в этой сессии»).

## Часть setup — включение провайдера email+пароль

Команда: `bash scripts/T-2-1_identity_platform_setup.sh setup`

Результат (`GET config` после `PATCH`):
```
"signIn": {
  "email": {
    "enabled": true,
    "passwordRequired": true
  },
  ...
},
"subtype": "IDENTITY_PLATFORM",
```
Self-signup: клиентский self-signup UI этой задачей не создаётся (frontend несёт только форму
`/login`, без формы регистрации) — управление доступом идёт исключительно через заведение
пользователей этим скриптом.

## Часть users — три тестовых пользователя с custom claim `role`

Команда: `LOMBARD_TEST_USER_PASSCODE='<пароль владельца>' bash
scripts/T-2-1_identity_platform_setup.sh users`

Вывод:
```
created uid=yyY1TtEUs7c8RKgHXUWQ1aHupNb2 email=test-owner@lombard-ops.test claims={"role": "owner"}
created uid=aHwjEP0r65R3L3JPm4cMLPi8Fyg2 email=test-manager@lombard-ops.test claims={"role": "manager"}
created uid=u9JpYPRNwsQ0PaKc5tSuH6oF2wO2 email=test-assessor@lombard-ops.test claims={"role": "assessor"}
```

Пароль тестовых пользователей задан владельцем в чате 2026-08-19, в репозиторий не попадает,
хранится только в переменной окружения на время запуска.

## Откат (не исполнен, справочно из брифа)

- Пользователи: `accounts:delete` (REST) или `firebase-admin auth.delete_user(uid)` по uid выше.
- Провайдер: `PATCH .../config?updateMask=signIn.email.enabled` с `{"signIn":{"email":{"enabled":false}}}`.
