#!/usr/bin/env bash
# scripts/T-1-1_deploy.sh — T-1-1, шаги 7-9 (класс B: применение DDL слоя
# сырья, деплой Cloud Run Job `raw-loader`, Cloud Scheduler job
# `raw-loader-trigger`)
#
# НЕ ИСПОЛНЯТЬ БЕЗ ОТДЕЛЬНОГО ПОДТВЕРЖДЕНИЯ ВЛАДЕЛЬЦА НА КАЖДУЮ ЧАСТЬ.
# Скрипт защищён от случайного запуска: без явного аргумента (`part1`,
# `part2` или `part3`) он ничего не делает и печатает подсказку. Один
# скрипт — на ШАГ брифа (05 §I «Один скрипт на ШАГ брифа»): часть 1 = шаг 7,
# часть 2 = шаг 8, часть 3 = шаг 9.
#
# Часть 1 (шаг 7, карточка подтверждения 1): применяет
#   `sql/ddl/lombard_ops_raw.sql` (сгенерирован `connector/generate_raw_ddl.py`,
#   не редактируется руками) — создаёт девять таблиц `raw_*` в датасете
#   `lombard_ops`. Откат: `bq rm -t lombard_ops.raw_<table>` по каждой из
#   девяти, датасет и остальные шесть таблиц не трогаются.
#
# Часть 2 (шаг 8, карточка подтверждения 2): синхронизирует РАНТАЙМ-копии
#   `connector/raw_loader/generate_raw_ddl.py` и `connector/raw_loader/mapping.json`
#   с источниками истины `connector/generate_raw_ddl.py`/`connector/mapping.json`
#   (обязательный шаг — деплой идёт `--source=connector/raw_loader`, контейнер
#   не видит файлы вне этого каталога, ADR-078 пп.4-5), затем деплоит Cloud
#   Run Job `raw-loader` явным билд-аккаунтом `lombard-build@…` (`ADR-077`
#   п.5). Откат: `gcloud run jobs delete raw-loader --region=europe-west3`.
#
# Часть 3 (шаг 9, карточка подтверждения 3): создаёт Cloud Scheduler job
#   `raw-loader-trigger`, HTTP-таргет на Cloud Run Jobs Admin API `:run` того
#   же job с OIDC-токеном SA `lombard-pipeline@…`, расписание 04:00
#   Asia/Bishkek (между агентским прогоном 03:00 и cf-daily 08:00). Перед
#   созданием job проверяет/выдаёт `roles/run.invoker` на job для той же SA —
#   без него вызов `:run` через OIDC отбивается 403 (Cloud Run Jobs Admin API
#   требует явный invoker-биндинг на job, не наследует IAM датасета/бакетов).
#   Откат: `gcloud scheduler jobs delete raw-loader-trigger --location=europe-west3`;
#   `gcloud run jobs remove-iam-policy-binding raw-loader --region=europe-west3
#    --member=serviceAccount:lombard-pipeline@… --role=roles/run.invoker` для
#   отзыва инвокера.

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
REGION="europe-west3"
SA_PIPELINE="lombard-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"
SA_BUILD="lombard-build@${PROJECT_ID}.iam.gserviceaccount.com"
JOB_NAME="raw-loader"
SCHEDULER_JOB="raw-loader-trigger"
DDL_FILE="sql/ddl/lombard_ops_raw.sql"

RAW_TABLES=(
  raw_contracts
  raw_contracts_terms
  raw_subjects
  raw_custom_fields_values
  raw_dir_custom_fields
  raw_tables_table
  raw_contract_states
  raw_deposit_types
  raw_operations
)

part1_apply_ddl() {
  echo "=== Часть 1 (шаг 7): применение DDL слоя сырья ${DDL_FILE} ==="

  if [ ! -f "${DDL_FILE}" ]; then
    echo "CONTEXT GAP: ${DDL_FILE} не найден — перегенерировать: python3 connector/generate_raw_ddl.py" >&2
    exit 1
  fi

  bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" < "${DDL_FILE}"

  echo "=== Приёмка части 1: bq show по каждой из девяти таблиц ==="
  for table in "${RAW_TABLES[@]}"; do
    echo "--- ${table} ---"
    bq show --project_id="${PROJECT_ID}" "lombard_ops.${table}"
  done
}

part2_deploy_job() {
  echo "=== Часть 2 (шаг 8): синхронизация рантайм-копий + деплой Cloud Run Job ${JOB_NAME} ==="

  cp connector/generate_raw_ddl.py connector/raw_loader/generate_raw_ddl.py
  cp connector/mapping.json connector/raw_loader/mapping.json
  echo "Копии синхронизированы: connector/raw_loader/{generate_raw_ddl.py,mapping.json}"

  echo "=== Проверка существования билд- и рантайм-аккаунтов перед подстановкой (ADR-077 п.2) ==="
  gcloud iam service-accounts describe "${SA_BUILD}" --format="value(email,uniqueId)"
  gcloud iam service-accounts describe "${SA_PIPELINE}" --format="value(email,uniqueId)"

  # ИСПРАВЛЕНО 2026-08-19: `gcloud run jobs deploy --source` в SDK 577.0.0 не несёт
  # флага --build-service-account вовсе (был в `gcloud functions deploy`, не в `run
  # jobs deploy`) — замерено `unrecognized arguments` при первом прогоне карточки 2.
  # Билд и деплой разнесены на два явных шага, билд-аккаунт называется в первом.
  IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${JOB_NAME}"

  # Без Dockerfile в connector/raw_loader/ — --tag требует Dockerfile (замерено
  # `Invalid value for [source]: Dockerfile required`), путь тот же, что
  # неявно шёл под `--source` — buildpacks через --pack.
  gcloud builds submit connector/raw_loader \
    --pack="image=${IMAGE}" \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${SA_BUILD}" \
    --gcs-log-dir="gs://${PROJECT_ID}-cfsource/build-logs" \
    --project="${PROJECT_ID}"

  gcloud run jobs deploy "${JOB_NAME}" \
    --image="${IMAGE}" \
    --region="${REGION}" \
    --service-account="${SA_PIPELINE}" \
    --set-env-vars="PROJECT_ID=${PROJECT_ID}" \
    --project="${PROJECT_ID}"

  echo "=== Приёмка части 2: gcloud run jobs describe ${JOB_NAME} ==="
  gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}"
}

part3_scheduler() {
  echo "=== Часть 3 (шаг 9): invoker-биндинг + Cloud Scheduler job ${SCHEDULER_JOB} ==="

  gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
    --region="${REGION}" \
    --member="serviceAccount:${SA_PIPELINE}" \
    --role="roles/run.invoker" \
    --project="${PROJECT_ID}"

  RUN_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

  gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
    --location="${REGION}" \
    --schedule="0 4 * * *" \
    --time-zone="Asia/Bishkek" \
    --uri="${RUN_URI}" \
    --http-method=POST \
    --oidc-service-account-email="${SA_PIPELINE}" \
    --oidc-token-audience="https://${REGION}-run.googleapis.com/" \
    --project="${PROJECT_ID}"

  echo "=== Приёмка части 3: gcloud scheduler jobs describe ${SCHEDULER_JOB} (расписание, часовой пояс) ==="
  gcloud scheduler jobs describe "${SCHEDULER_JOB}" --location="${REGION}" --project="${PROJECT_ID}"
}

part3b_fix_scheduler_auth() {
  echo "=== Часть 3-Б (исправление шага 9 по факту провала шага 10): OIDC -> OAuth ==="
  # Замерено 2026-08-20: цель вызова — europe-west3-run.googleapis.com, хост *.googleapis.com
  # (Cloud Run Jobs Admin API), а не прямой URL сервиса. `gcloud scheduler jobs create http
  # --help` дословно: OAuth обязателен для целей *.googleapis.com, OIDC отбивается 401
  # UNAUTHENTICATED (лог AttemptFinished, reference/T-1-1_raw_loader_run_2026-08-19.md).
  # roles/run.invoker (часть 3, п.1) не трогается — он верный и не был причиной отказа.

  RUN_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

  gcloud scheduler jobs delete "${SCHEDULER_JOB}" --location="${REGION}" --project="${PROJECT_ID}" --quiet

  gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
    --location="${REGION}" \
    --schedule="0 4 * * *" \
    --time-zone="Asia/Bishkek" \
    --uri="${RUN_URI}" \
    --http-method=POST \
    --oauth-service-account-email="${SA_PIPELINE}" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
    --project="${PROJECT_ID}"

  echo "=== Приёмка части 3-Б: gcloud scheduler jobs describe ${SCHEDULER_JOB} (oauthToken, не oidcToken) ==="
  gcloud scheduler jobs describe "${SCHEDULER_JOB}" --location="${REGION}" --project="${PROJECT_ID}"
}

case "${1:-}" in
  part1) part1_apply_ddl ;;
  part2) part2_deploy_job ;;
  part3) part3_scheduler ;;
  part3b) part3b_fix_scheduler_auth ;;
  *)
    echo "Использование: $0 part1   # шаг 7, после карточки подтверждения 1 (DDL)"
    echo "               $0 part2   # шаг 8, после карточки подтверждения 2 (Cloud Run Job)"
    echo "               $0 part3   # шаг 9, после карточки подтверждения 3 (Cloud Scheduler)"
    echo "               $0 part3b  # исправление шага 9 (OIDC -> OAuth), после карточки подтверждения 3-Б"
    echo "Без аргумента скрипт НИЧЕГО не делает — защита от случайного запуска."
    exit 1
    ;;
esac
