#!/usr/bin/env bash
# scripts/T-2-4_load_catalog.sh — T-2-4, шаги 10→11 (класс B: ALTER TABLE lombard_ops.vehicle_catalog
# + bq load сида в реальный датасет lombard_ops, europe-west3).
#
# НЕ ИСПОЛНЯТЬ БЕЗ ОТДЕЛЬНОГО ПОДТВЕРЖДЕНИЯ ВЛАДЕЛЬЦА. Без явного аргумента ничего не делает.
# Диагностика (before/after) — отдельные команды от самого изменения (05 §I, «Наблюдение»).
#
# Что исполняется:
#   1) `bq query` — счёт строк vehicle_catalog ДО (ожидается 0)
#   2) `bq query --nouse_legacy_sql` — ALTER TABLE lombard_ops.vehicle_catalog
#        ADD COLUMN price_source STRING, ADD COLUMN comment STRING
#      (comment уже присутствовал бы, если бы таблица создавалась впервые этим DDL — на прод-датасете
#      таблица уже существует без этих колонок, отсюда ALTER, а не пересоздание)
#   3) `bq load` — data_inbox/vehicle_catalog_seed.json (newline-delimited JSON, без autodetect,
#      явная схема из sql/ddl/lombard_ops.sql) в lombard_ops.vehicle_catalog
#   4) `bq query` — счёт строк ПОСЛЕ, распределение по liquidity_class, счёт по price_source
# На каком объекте: PROJECT_ID=project-c451b48a-07ae-4de4-961, датасет lombard_ops (europe-west3),
#   таблица vehicle_catalog.
# Чем откатывается:
#   - схема: `ALTER TABLE lombard_ops.vehicle_catalog DROP COLUMN price_source, DROP COLUMN comment`
#   - данные: `DELETE FROM lombard_ops.vehicle_catalog WHERE TRUE` (снимок этого запуска —
#     все строки несут updated_at этого прогона, таблица до загрузки пуста согласно диагностике
#     «до», удаление всех строк равно откату к состоянию «до»)

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
LOCATION="europe-west3"
DATASET="lombard_ops"
TABLE="vehicle_catalog"
SEED_FILE="data_inbox/vehicle_catalog_seed.json"
# Схема НЕ передаётся явно: таблица lombard_ops.vehicle_catalog уже существует (ALTER TABLE выше
# применяется к ней же) — bq load использует схему существующей таблицы (документированное
# поведение: "This schema should be omitted if the table already has one"). Инлайн-схема bq load
# (name:type через запятую) не поддерживает MODE, а make/model в этой таблице REQUIRED — попытка
# передать текстовую схему валится с "Invalid schema entry: make:STRING:REQUIRED".

diag_before() {
  echo "=== Диагностика ДО (ожидается 0 строк) ==="
  bq query --project_id="${PROJECT_ID}" --location="${LOCATION}" --nouse_legacy_sql \
    "SELECT COUNT(*) AS row_count FROM \`${DATASET}.${TABLE}\`"
}

alter_schema() {
  echo "=== ALTER TABLE: добавление price_source, comment ==="
  bq query --project_id="${PROJECT_ID}" --location="${LOCATION}" --nouse_legacy_sql \
    "ALTER TABLE \`${DATASET}.${TABLE}\` ADD COLUMN price_source STRING, ADD COLUMN comment STRING"
}

load_seed() {
  if [[ ! -f "${SEED_FILE}" ]]; then
    echo "CONTEXT GAP: ${SEED_FILE} не найден — прогнать tools/T-2-4_build_seed.py заново"
    exit 1
  fi
  echo "=== bq load: ${SEED_FILE} → ${DATASET}.${TABLE} (явная схема, без autodetect) ==="
  bq load --project_id="${PROJECT_ID}" --location="${LOCATION}" \
    --source_format=NEWLINE_DELIMITED_JSON \
    "${DATASET}.${TABLE}" \
    "${SEED_FILE}"
}

diag_after() {
  echo "=== Диагностика ПОСЛЕ: счёт строк ==="
  bq query --project_id="${PROJECT_ID}" --location="${LOCATION}" --nouse_legacy_sql \
    "SELECT COUNT(*) AS row_count FROM \`${DATASET}.${TABLE}\`"
  echo "=== Диагностика ПОСЛЕ: распределение по liquidity_class ==="
  bq query --project_id="${PROJECT_ID}" --location="${LOCATION}" --nouse_legacy_sql \
    "SELECT liquidity_class, COUNT(*) AS n FROM \`${DATASET}.${TABLE}\` GROUP BY liquidity_class ORDER BY liquidity_class"
  echo "=== Диагностика ПОСЛЕ: счёт по price_source ==="
  bq query --project_id="${PROJECT_ID}" --location="${LOCATION}" --nouse_legacy_sql \
    "SELECT price_source, COUNT(*) AS n FROM \`${DATASET}.${TABLE}\` GROUP BY price_source ORDER BY price_source"
}

case "${1:-}" in
  diag-before) diag_before ;;
  alter) alter_schema ;;
  load) load_seed ;;
  diag-after) diag_after ;;
  all)
    diag_before
    alter_schema
    load_seed
    diag_after
    ;;
  *)
    echo "Использование: $0 {diag-before|alter|load|diag-after|all}"
    echo "Без аргумента скрипт НИЧЕГО не делает — защита от случайного запуска."
    exit 1
    ;;
esac
