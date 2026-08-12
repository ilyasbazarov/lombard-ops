#!/usr/bin/env bash
# T-0-7 · GCP-фундамент в europe-west3 (ADR-046)
# Воспроизводимый блок: один раздел на шаг брифа briefs/T-0-7.md. Не исполняется целиком слепо —
# каждый шаг — отдельное подтверждение владельца (класс B).
set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
REGION="europe-west3"
DATASET="lombard_ops"

# --- Шаг 2 — включение API (класс B) ---
step2_enable_apis() {
  gcloud services enable \
    bigquery.googleapis.com \
    storage.googleapis.com \
    run.googleapis.com \
    cloudfunctions.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    iam.googleapis.com \
    --project="${PROJECT_ID}"
  gcloud services list --enabled --project="${PROJECT_ID}"
}

# --- Шаг 3 — датасет и таблицы (класс B) ---
step3_dataset_and_tables() {
  bq mk --location="${REGION}" "${PROJECT_ID}:${DATASET}"
  for f in "$(dirname "$0")/../sql/ddl/lombard_ops.sql"; do :; done
  bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" < "$(dirname "$0")/../sql/ddl/lombard_ops.sql"
  bq show --format=prettyjson "${PROJECT_ID}:${DATASET}"
  bq ls "${PROJECT_ID}:${DATASET}"
}

# --- Шаг 4 — бакеты (класс B) ---
step4_buckets() {
  for suffix in photos config cfsource; do
    gcloud storage buckets create "gs://${PROJECT_ID}-${suffix}" \
      --project="${PROJECT_ID}" \
      --location="${REGION}" \
      --uniform-bucket-level-access \
      --public-access-prevention
  done
  for suffix in photos config cfsource; do
    gcloud storage buckets describe "gs://${PROJECT_ID}-${suffix}" \
      --format="value(name,location,public_access_prevention)"
  done
}

# --- Шаг 5 — сервисный аккаунт и роли (класс B) ---
step5_service_account() {
  gcloud iam service-accounts create lombard-pipeline \
    --project="${PROJECT_ID}" \
    --display-name="lombard-pipeline"

  local SA="lombard-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"

  # BigQuery: запись в пределах датасета — dataset-level ACL, не project-level роль.
  # `bq add-iam-policy-binding` на датасете упирается в "This feature requires allowlisting"
  # (fine-grained BQ IAM не разрешён в проекте) — используется классический dataset ACL.
  bq show --format=prettyjson "${PROJECT_ID}:${DATASET}" > /tmp/lombard_ops_current.json
  python3 - <<PY
import json
d = json.load(open('/tmp/lombard_ops_current.json'))
access = d.get('access', [])
access.append({"role": "WRITER", "userByEmail": "${SA}"})
json.dump({"access": access}, open('/tmp/lombard_ops_new_access.json', 'w'))
PY
  bq update --source=/tmp/lombard_ops_new_access.json "${PROJECT_ID}:${DATASET}"

  # чтение и запись в три бакета — bucket-level IAM
  for suffix in photos config cfsource; do
    gcloud storage buckets add-iam-policy-binding "gs://${PROJECT_ID}-${suffix}" \
      --member="serviceAccount:${SA}" \
      --role="roles/storage.objectAdmin"
  done

  # чтение секретов — project-level (Secret Manager не поддерживает более узкий scope без секретов ещё не созданных)
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None

  gcloud projects get-iam-policy "${PROJECT_ID}" \
    --flatten="bindings[].members" \
    --filter="bindings.members:${SA}" \
    --format="table(bindings.role)"
}

# --- Шаг 6 — секреты-заглушки (класс B) ---
step6_secrets() {
  for name in telegram-bot-token firebird-readonly-creds chat_id; do
    printf 'PLACEHOLDER' | gcloud secrets create "${name}" \
      --project="${PROJECT_ID}" \
      --replication-policy="user-managed" \
      --locations="${REGION}" \
      --data-file=-
  done
  gcloud secrets list --project="${PROJECT_ID}"
  for name in telegram-bot-token firebird-readonly-creds chat_id; do
    gcloud secrets versions list "${name}" --project="${PROJECT_ID}"
  done
}

# --- Шаг 7 — сплошная проверка региона (класс A, только чтение) ---
step7_region_sweep() {
  echo "=== Датасеты BigQuery: имя и локация ==="
  bq ls --format=prettyjson -d "${PROJECT_ID}" | python3 -c "import json,sys; [print(d['id'], d.get('location','?')) for d in json.load(sys.stdin)]"
  echo "=== Бакеты GCS: имя и локация ==="
  gcloud storage buckets list --project="${PROJECT_ID}" --format="table(name,location)"
}

"$@"
