# ИСПОЛНЕНИЕ · T-1-0 шаг 7 · IAM-биндинг invoker + Cloud Scheduler · 2026-08-18

**Класс B, карточка подтверждена владельцем.** Основание — карточка шага 7 после закрытия
шага 6. **Коммит на входе:** `d203768`.

---

## 1. Расхождение текста запуска с фактом платформы (`ADR-027`)

Комментарий скрипта (`scripts/T-1-0_deploy.sh:15`) и бриф (`briefs/T-1-0.md:235`) называют
роль биндинга `roles/cloudfunctions.invoker` дословно. Фактически `functions
add-invoker-policy-binding` на функции 2-го поколения выдал:

```
$ gcloud functions add-invoker-policy-binding cf-daily --region=europe-west3 \
    --member=serviceAccount:lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com \
    --project=project-c451b48a-07ae-4de4-961
bindings:
- members:
  - serviceAccount:lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
  role: roles/run.invoker
```

**Расхождение — платформенное, не дефект исполнения.** Cloud Functions Gen2 — тонкая обёртка
над Cloud Run; вызов вызывающей функции идёт через Cloud Run-сервис, поэтому платформа сама
транслирует запрошенный инвокер в `roles/run.invoker` на соответствующем Cloud Run-сервисе,
а не в `roles/cloudfunctions.invoker`. Действие, которое требовалось (право вызова конкретно
`cf-daily` для `lombard-pipeline`), выдано; отличается только имя роли платформенного слоя,
через который это реализовано. Команда деплоя названа брифом верно (`add-invoker-policy-binding`
на объекте `cf-daily`), исполнена той же командой.

## 2. Cloud Scheduler job

```
$ gcloud scheduler jobs describe cf-daily-trigger --location=europe-west3 \
    --project=project-c451b48a-07ae-4de4-961
schedule: 0 8 * * *
timeZone: Asia/Bishkek
scheduleTime: '2026-08-19T02:00:00Z'
state: ENABLED
httpTarget:
  httpMethod: POST
  uri: https://cf-daily-ixy63xgujq-ey.a.run.app/
  oidcToken:
    audience: https://cf-daily-ixy63xgujq-ey.a.run.app
    serviceAccountEmail: lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
```

`08:00 Asia/Bishkek` (UTC+6) → `02:00 UTC` — `scheduleTime` совпадает побуквенно. `state: ENABLED`.
Триггер, аудитория и SA — те, что называет `01_ARCHITECTURE.md §2`.

## 3. Шаг 7 закрыт; что этим НЕ установлено

Первый реальный запуск по расписанию — не раньше `2026-08-19T02:00:00Z` (по Бишкеку, `19.08 08:00`).
Работоспособность нитки (а)–(е) целиком на живых данных не проверена — предмет наблюдения после
первого срабатывания, шаги 8–9 брифа.
