#!/usr/bin/env bash
# T-0-8 · Шаг 5-А ПОЛНОСТЬЮ, пункты 1–5 (`ADR-050`, `ADR-051`, ПОПРАВКА 3 брифа) — класс B, Cloud Shell.
#
# Что делает ЭТОТ скрипт:
#   1) read-only: constraints/iam.allowedPolicyMemberDomains --effective
#   2) read-only: включённые сервисы, печать совпадений по iamcredentials/sts,
#      включение недостающих (iamcredentials уже подтянут T-0-7 зависимостью — это сверка)
#   3) СОЗДАНИЕ пула федерации (workload-identity-pools create)
#   4) СОЗДАНИЕ OIDC-провайдера с --issuer-uri, --attribute-mapping, --attribute-condition,
#      --jwk-json-path (файл JWKS — вход, см. функцию write_jwks_file ниже)
#   5) ПРИВЯЗКА роли roles/iam.workloadIdentityUser на lombard-pipeline@ через role binding
#
# Пункты 1-3 ИСПОЛНЕНЫ 2026-08-13 (см. reference/T-0-8_federation_setup_2026-08-13.md) — функции
# step1/step2/step3 остаются в файле как факт исполнения, повторному запуску не подлежат
# (step3_create_pool на существующем пуле отобьёт ошибкой "already exists" — это ожидаемо).
#
# Пункты 4-5 ПОДГОТОВЛЕНЫ этой сессией (класс A: написание команд без применения), НЕ исполнены.
# Значения на входе:
#   --issuer-uri              = https://erp-agent.lombard-ops.invalid (Q-22 закрыт ADR-051, готовая строка)
#   JWKS (--jwk-json-path)    = содержимое ТОЧНО с шага 5-Б (kid=lombard-agent-20260813),
#                                записывается функцией write_jwks_file в локальный файл
#   субъект агента (sub)      = lombard-agent-erp01 — назначен ЭТОЙ сессией как внутренний
#                                идентификатор (не секрет, не факт о клиенте); ОБЯЗАН совпасть
#                                побуквенно со значением LOMBARD_AGENT_SUBJECT конфига агента
#                                на сервере (шаг 6) — расхождение даёт отказ обмена токена
#
# НЕ исполнять без отдельного подтверждения Ilyas по карточке. Пункты 4 и 5 — ОДНА карточка
# (брифом названы как одно замыкающее действие), каждая функция запускается по одной командой,
# не всё подряд слепо.
#
# Порядок ВНУТРИ шага обязателен (брифинг): read-only 1, read-only 2, потом создание (3, затем 4-5).
# Пункт 1 действует (enforce на allowedPolicyMemberDomains) → СТОП и вопрос архитектору,
# дальше не идти (карточка ниже).
#
# Откат пунктов 4-5 (команды пишутся ДО создания, по требованию карточки):
#   rollback_step5_remove_binding   — снимает role binding
#   rollback_step4_delete_provider  — удаляет провайдер
# (порядок отката обратный созданию: сначала снять привязку, потом удалить провайдер)

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
PROJECT_NUMBER="450925595005"
LOCATION="global"
POOL_ID="lombard-agent-federation-pool"
POOL_DISPLAY_NAME="Lombard agent federation pool"
POOL_DESCRIPTION="T-0-8: пул федерации для JWT-подписи агента на сервере ERP (ADR-050)"
PROVIDER_ID="lombard-agent-jwt-provider"
PROVIDER_DISPLAY_NAME="Lombard agent JWT provider"
PROVIDER_DESCRIPTION="T-0-8: OIDC-провайдер для самоподписанного JWT агента на сервере ERP (ADR-050, ADR-051)"
ISSUER_URI="https://erp-agent.lombard-ops.invalid"
AGENT_SUBJECT="lombard-agent-erp01"
JWKS_LOCAL_PATH="${HOME}/T-0-8_jwks.json"
SA_EMAIL="lombard-pipeline@${PROJECT_ID}.iam.gserviceaccount.com"

# --- Пункт 1 (read-only, ОБЯЗАТЕЛЬНО ПЕРВЫМ) ---
step1_check_allowed_policy_member_domains() {
  gcloud org-policies describe constraints/iam.allowedPolicyMemberDomains \
    --project="${PROJECT_ID}" \
    --effective
}

# --- Пункт 2 (read-only) ---
step2_check_enabled_services() {
  gcloud services list --enabled --project="${PROJECT_ID}" \
    | grep -E "iamcredentials|sts" || {
      echo "СТРОК ПО iamcredentials/sts НЕ НАЙДЕНО — это отказ поиска, не факт \"сервисы выключены\"."
      echo "Обратный контроль (список целиком) для проверки исправности grep:"
      gcloud services list --enabled --project="${PROJECT_ID}"
      exit 1
    }
}

# Включение недостающих сервисов — исполняется ТОЛЬКО если шаг 2 показал отсутствие строки.
step2_enable_missing_services() {
  gcloud services enable iamcredentials.googleapis.com sts.googleapis.com \
    --project="${PROJECT_ID}"
  gcloud services list --enabled --project="${PROJECT_ID}" | grep -E "iamcredentials|sts"
}

# --- Пункт 3 (СОЗДАНИЕ пула федерации) ---
step3_create_pool() {
  gcloud iam workload-identity-pools create "${POOL_ID}" \
    --project="${PROJECT_ID}" \
    --location="${LOCATION}" \
    --display-name="${POOL_DISPLAY_NAME}" \
    --description="${POOL_DESCRIPTION}"
  gcloud iam workload-identity-pools describe "${POOL_ID}" \
    --project="${PROJECT_ID}" \
    --location="${LOCATION}"
}

# --- Откат пункта 3 (команда пишется ДО создания, по требованию карточки) ---
rollback_step3_delete_pool() {
  gcloud iam workload-identity-pools delete "${POOL_ID}" \
    --project="${PROJECT_ID}" \
    --location="${LOCATION}" \
    --quiet
}

# --- Вход пункта 4: записать локальный файл JWKS ТОЧНО с содержимым шага 5-Б ---
# Содержимое дословно из reference/T-0-8_federation_setup_2026-08-13.md, раздел «Шаг 5-Б»,
# kid=lombard-agent-20260813. Файл создаётся ЛОКАЛЬНО (Cloud Shell/локальная машина владельца),
# не на сервере ERP — приватного ключа в нём нет, это открытая часть, не секрет.
write_jwks_file() {
  cat > "${JWKS_LOCAL_PATH}" <<'JWKS_EOF'
{"keys": [{"kty": "RSA", "alg": "RS256", "use": "sig", "kid": "lombard-agent-20260813", "n": "sAjRj2yWNrtbc9eBTp_BX0jWfCG68-tMtBqMrB-RCRYPZDLyWrRVVhdhIq9dlLLSI0n663XM8OevL4_tOxfxL6qrYaJ6VU9PnqATJtl7_1bJgaZ89HDlXMJUNY6qitZHv7KMH9WTI8ZK87clvoh5_5Jov_DqsR169fW9SqgI-QTQMUXaVKseDO9oSjLfR6MziaLrwb4jSufksLAo2SkEewJb0T1YDlo3jOkO6s-hct1aviW3DH3VgowsTCjObJiTJV7EB0SGCaHgXsyuC2Cg76Im6eHbp7OmGrdvPK4toRsVDUbzrcoMxSnurNrBMOTBLTOh4Cpxd4IFtFqPbaEyCw", "e": "AQAB"}]}
JWKS_EOF
  echo "JWKS записан: ${JWKS_LOCAL_PATH}"
  cat "${JWKS_LOCAL_PATH}"
}

# --- Пункт 4 (СОЗДАНИЕ OIDC-провайдера) ---
# Предусловие: write_jwks_file уже выполнена, файл JWKS существует по JWKS_LOCAL_PATH.
step4_create_provider() {
  if [[ ! -s "${JWKS_LOCAL_PATH}" ]]; then
    echo "СТОП: файл JWKS отсутствует или пуст (${JWKS_LOCAL_PATH}) — сначала write_jwks_file" >&2
    exit 1
  fi
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
    --project="${PROJECT_ID}" \
    --location="${LOCATION}" \
    --workload-identity-pool="${POOL_ID}" \
    --display-name="${PROVIDER_DISPLAY_NAME}" \
    --description="${PROVIDER_DESCRIPTION}" \
    --issuer-uri="${ISSUER_URI}" \
    --attribute-mapping="google.subject=assertion.sub" \
    --attribute-condition="assertion.sub == '${AGENT_SUBJECT}'" \
    --jwk-json-path="${JWKS_LOCAL_PATH}"
  gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
    --project="${PROJECT_ID}" \
    --location="${LOCATION}" \
    --workload-identity-pool="${POOL_ID}"
}

# --- Откат пункта 4 (команда пишется ДО создания, по требованию карточки) ---
rollback_step4_delete_provider() {
  gcloud iam workload-identity-pools providers delete "${PROVIDER_ID}" \
    --project="${PROJECT_ID}" \
    --location="${LOCATION}" \
    --workload-identity-pool="${POOL_ID}" \
    --quiet
}

# --- Пункт 5 (ПРИВЯЗКА роли на существующий SA конвейера) ---
# Новых ролей SA не выдаётся (11_INFRA_FACTS) — только roles/iam.workloadIdentityUser внешнему principal.
step5_bind_role() {
  local member="principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/${LOCATION}/workloadIdentityPools/${POOL_ID}/subject/${AGENT_SUBJECT}"
  gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
    --project="${PROJECT_ID}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="${member}"
  gcloud iam service-accounts get-iam-policy "${SA_EMAIL}" --project="${PROJECT_ID}"
}

# --- Откат пункта 5 (команда пишется ДО создания, по требованию карточки) ---
rollback_step5_remove_binding() {
  local member="principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/${LOCATION}/workloadIdentityPools/${POOL_ID}/subject/${AGENT_SUBJECT}"
  gcloud iam service-accounts remove-iam-policy-binding "${SA_EMAIL}" \
    --project="${PROJECT_ID}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="${member}"
}

usage() {
  cat <<'EOF'
Запуск ПО ОДНОЙ функции за раз, каждая — отдельное подтверждение:
  step1_check_allowed_policy_member_domains
  step2_check_enabled_services
  step2_enable_missing_services   # только если шаг 2 не нашёл iamcredentials/sts
  step3_create_pool
  rollback_step3_delete_pool      # только для отката, не часть штатного прогона

  write_jwks_file                 # вход пункта 4: пишет локальный файл JWKS (шаг 5-Б, дословно)
  step4_create_provider           # создаёт OIDC-провайдер (требует write_jwks_file ДО себя)
  rollback_step4_delete_provider  # откат пункта 4

  step5_bind_role                 # role binding на lombard-pipeline@ (требует step4 ДО себя)
  rollback_step5_remove_binding   # откат пункта 5

Пункты 4 и 5 — ОДНА карточка подтверждения (замыкающее действие шага 5-А).

Пример: source T-0-8_step5a_federation_pool.sh && step1_check_allowed_policy_member_domains
EOF
}

if [[ "${1:-}" != "" ]]; then
  "$1"
else
  usage
fi
