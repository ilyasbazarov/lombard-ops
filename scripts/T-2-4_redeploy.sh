#!/usr/bin/env bash
# scripts/T-2-4_redeploy.sh — T-2-4, шаги 12→13 (класс B: редеплой app-lombard, теперь несущего
# эндпоинт GET /api/catalog и экран /catalog). Тот же билд-аккаунт и та же команда, что
# scripts/T-2-1_deploy.sh — скрипт свой, чужой не правится (ADR-076/ADR-077).
#
# НЕ ИСПОЛНЯТЬ БЕЗ ОТДЕЛЬНОГО ПОДТВЕРЖДЕНИЯ ВЛАДЕЛЬЦА. Без явного аргумента ничего не делает.
#
# Что исполняется: `gcloud run deploy app-lombard --source=app` из чистой папки app/ (не из корня
#   репозитория), билд-аккаунт lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
#   (`--build-service-account`, обязательная проверка `iam service-accounts describe` перед
#   подстановкой — ADR-077 п.13), runtime lombard-pipeline@... (тот же аккаунт читает BigQuery для
#   /api/catalog — новых прав не требуется, 11_INFRA_FACTS.md, раздел «GCP»).
# На каком объекте: PROJECT_ID=project-c451b48a-07ae-4de4-961, регион europe-west3, Cloud Run
#   service app-lombard.
# Чем откатывается: `gcloud run services update-traffic app-lombard --region=europe-west3
#   --to-revisions=<предыдущая_ревизия>=100` (предыдущая ревизия — из `gcloud run revisions list
#   --service=app-lombard --region=europe-west3` ДО этого запуска); либо повторный `gcloud run
#   deploy --source=app` с прежним коммитом, если ревизия уже удалена.

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
REGION="europe-west3"
SERVICE_NAME="app-lombard"
BUILD_SA="lombard-build@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="lombard-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"

redeploy() {
  echo "=== Ревизия ДО (для отката) ==="
  gcloud run revisions list --service="${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}"

  echo "=== Проверка билд-аккаунта перед подстановкой (ADR-077 п.13) ==="
  gcloud iam service-accounts describe "${BUILD_SA}" --project="${PROJECT_ID}"

  echo "=== Редеплой ${SERVICE_NAME} из app/ (несёт /api/catalog и /catalog) ==="
  gcloud run deploy "${SERVICE_NAME}" \
    --source=app \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --service-account="${RUNTIME_SA}" \
    --build-service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
    --allow-unauthenticated

  echo "=== Приёмка шага 13: describe (ожидается READY, URL, новая ревизия) ==="
  gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"
}

case "${1:-}" in
  deploy) redeploy ;;
  *)
    echo "Использование: $0 deploy   # редеплой app-lombard (шаг 12→13)"
    echo "Без аргумента скрипт НИЧЕГО не делает — защита от случайного запуска."
    exit 1
    ;;
esac
