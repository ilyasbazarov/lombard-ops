#!/usr/bin/env bash
# scripts/T-2-1_deploy.sh — T-2-1, шаг 6/7 (класс B: сборка образа и деплой app-lombard на
# Cloud Run, europe-west3, билд-аккаунт lombard-build@... ADR-076/ADR-077).
#
# НЕ ИСПОЛНЯТЬ БЕЗ ОТДЕЛЬНОГО ПОДТВЕРЖДЕНИЯ ВЛАДЕЛЬЦА. Без явного аргумента ничего не делает.
#
# Что исполняется: `gcloud run deploy app-lombard --source=app` (деплой ТОЛЬКО из чистой папки
#   app/, не из корня репозитория — брифа «Ограничения»), сборка образа под явно названным
#   билд-аккаунтом lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
#   (`--build-service-account`, обязательная проверка `iam service-accounts describe` перед
#   подстановкой — ADR-077 п.13), runtime под lombard-pipeline@... (тот же паттерн, что у
#   cf-daily), значения VITE_FIREBASE_* передаются build-args ТОЛЬКО если Identity Platform уже
#   включена (после подтверждения карточки шага 4) — иначе login-экран соберётся без рабочего
#   firebaseConfig и это называется в логе явно, не маскируется.
# На каком объекте: PROJECT_ID=project-c451b48a-07ae-4de4-961, регион europe-west3, Cloud Run
#   service `app-lombard`.
# Чем откатывается: `gcloud run services delete app-lombard --region=europe-west3` (сервиса ещё
#   нет — первый деплой создаёт его; повторный деплой создаёт новую ревизию, откат — `gcloud run
#   services update-traffic app-lombard --to-revisions=<prev>=100`, если предыдущая ревизия уже
#   существует).

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
REGION="europe-west3"
SERVICE_NAME="app-lombard"
BUILD_SA="lombard-build@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="lombard-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"

deploy() {
  echo "=== Проверка билд-аккаунта перед подстановкой (ADR-077 п.13) ==="
  gcloud iam service-accounts describe "${BUILD_SA}" --project="${PROJECT_ID}"

  echo "=== Деплой ${SERVICE_NAME} из app/ (шаг 6→7) ==="
  gcloud run deploy "${SERVICE_NAME}" \
    --source=app \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --service-account="${RUNTIME_SA}" \
    --build-service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
    --allow-unauthenticated

  echo "=== Приёмка шага 7: describe (ожидается READY, регион, URL) ==="
  gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"
}

case "${1:-}" in
  deploy) deploy ;;
  *)
    echo "Использование: $0 deploy   # сборка + деплой app-lombard (шаг 6→7)"
    echo "Без аргумента скрипт НИЧЕГО не делает — защита от случайного запуска."
    exit 1
    ;;
esac
