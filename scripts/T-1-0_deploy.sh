#!/usr/bin/env bash
# scripts/T-1-0_deploy.sh — T-1-0, шаги 6-7 (класс B: деплой Cloud Function,
# IAM-биндинг вызова, Cloud Scheduler job)
#
# НЕ ИСПОЛНЯТЬ БЕЗ ОТДЕЛЬНОГО ПОДТВЕРЖДЕНИЯ ВЛАДЕЛЬЦА НА КАЖДУЮ ЧАСТЬ.
# Скрипт защищён от случайного запуска: без явного аргумента (`part1` или
# `part2`) он ничего не делает и печатает подсказку. Один скрипт — на ШАГ
# брифа (05 §I «Один скрипт на ШАГ брифа»): часть 1 = шаг 6, часть 2 = шаг 7.
#
# Часть 1 (шаг 6, карточка подтверждения 1): деплой `functions/cf_daily/` как
#   Cloud Function Gen2 HTTP-триггер `cf-daily`, регион europe-west3, SA
#   lombard-pipeline@..., переменная окружения PROJECT_ID.
#   Откат: `gcloud functions delete cf-daily --region=europe-west3`.
#
# Часть 2 (шаг 7, карточка подтверждения 2): биндинг `roles/cloudfunctions.invoker`
#   на cf-daily для SA lombard-pipeline@...; создание Cloud Scheduler job
#   `cf-daily-trigger`, HTTP-таргет на URL функции с OIDC-токеном той же SA,
#   расписание 08:00 Asia/Bishkek (`01_ARCHITECTURE.md §2`).
#   Откат: `gcloud scheduler jobs delete cf-daily-trigger --location=europe-west3`;
#   `gcloud functions remove-invoker-policy-binding cf-daily --region=europe-west3
#    --member=serviceAccount:lombard-pipeline@...` для отзыва инвокера.

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
REGION="europe-west3"
SA_EMAIL="lombard-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"
FUNCTION_NAME="cf-daily"
SCHEDULER_JOB="cf-daily-trigger"

part1_deploy_function() {
  echo "=== Часть 1 (шаг 6): деплой Cloud Function ${FUNCTION_NAME} ==="

  gcloud functions deploy "${FUNCTION_NAME}" \
    --gen2 \
    --runtime=python312 \
    --region="${REGION}" \
    --source=functions/cf_daily \
    --entry-point=cf_daily \
    --trigger-http \
    --no-allow-unauthenticated \
    --service-account="${SA_EMAIL}" \
    --set-env-vars="PROJECT_ID=${PROJECT_ID}" \
    --build-service-account=projects/project-c451b48a-07ae-4de4-961/serviceAccounts/450925595005@cloudbuild.gserviceaccount.com \
    --project="${PROJECT_ID}"

  echo "=== Приёмка части 1: describe (ожидается ACTIVE, URL) ==="
  gcloud functions describe "${FUNCTION_NAME}" \
    --region="${REGION}" \
    --gen2 \
    --project="${PROJECT_ID}"
}

part2_scheduler_and_iam() {
  echo "=== Часть 2 (шаг 7): IAM-биндинг invoker + Cloud Scheduler job ==="

  gcloud functions add-invoker-policy-binding "${FUNCTION_NAME}" \
    --region="${REGION}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --project="${PROJECT_ID}"

  FUNCTION_URL=$(gcloud functions describe "${FUNCTION_NAME}" \
    --region="${REGION}" \
    --gen2 \
    --project="${PROJECT_ID}" \
    --format='value(serviceConfig.uri)')

  if [ -z "${FUNCTION_URL}" ]; then
    echo "CONTEXT GAP: URL функции ${FUNCTION_NAME} не получен describe-выводом — часть 2 остановлена" >&2
    exit 1
  fi

  gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
    --location="${REGION}" \
    --schedule="0 8 * * *" \
    --time-zone="Asia/Bishkek" \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --oidc-service-account-email="${SA_EMAIL}" \
    --oidc-token-audience="${FUNCTION_URL}" \
    --project="${PROJECT_ID}"

  echo "=== Приёмка части 2: scheduler jobs describe (расписание, часовой пояс) ==="
  gcloud scheduler jobs describe "${SCHEDULER_JOB}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}"
}

case "${1:-}" in
  part1) part1_deploy_function ;;
  part2) part2_scheduler_and_iam ;;
  *)
    echo "Использование: $0 part1   # шаг 6, после карточки подтверждения 1"
    echo "               $0 part2   # шаг 7, после карточки подтверждения 2"
    echo "Без аргумента скрипт НИЧЕГО не делает — защита от случайного запуска."
    exit 1
    ;;
esac
