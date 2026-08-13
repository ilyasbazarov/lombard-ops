#!/usr/bin/env bash
# T-0-8 · Шаг 5-А, пункты 1–3 ТОЛЬКО (`ADR-050`, ПОПРАВКА 3 брифа) — класс B, Cloud Shell.
#
# Что делает ЭТОТ скрипт (и только это):
#   1) read-only: constraints/iam.allowedPolicyMemberDomains --effective
#   2) read-only: включённые сервисы, печать совпадений по iamcredentials/sts,
#      включение недостающих (iamcredentials уже подтянут T-0-7 зависимостью — это сверка)
#   3) СОЗДАНИЕ пула федерации (workload-identity-pools create)
#
# Пункт 4 (создание OIDC-провайдера, --issuer-uri, --jwk-json-path) и пункт 5 (role binding)
# в этот скрипт НЕ входят — они ждут issuer-uri (CONTEXT GAP, см. сессию) и файл JWKS (шаг 5-Б).
#
# НЕ исполнять без отдельного подтверждения Ilyas по карточке. Каждая функция — один шаг,
# запускать по одной, не всё подряд слепо.
#
# Порядок ВНУТРИ шага обязателен (брифинг): read-only 1, read-only 2, потом создание.
# Пункт 1 действует (enforce на allowedPolicyMemberDomains) → СТОП и вопрос архитектору,
# дальше не идти (карточка ниже).

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"
LOCATION="global"
POOL_ID="lombard-agent-federation-pool"
POOL_DISPLAY_NAME="Lombard agent federation pool"
POOL_DESCRIPTION="T-0-8: пул федерации для JWT-подписи агента на сервере ERP (ADR-050)"

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

usage() {
  cat <<'EOF'
Запуск ПО ОДНОЙ функции за раз, каждая — отдельное подтверждение:
  step1_check_allowed_policy_member_domains
  step2_check_enabled_services
  step2_enable_missing_services   # только если шаг 2 не нашёл iamcredentials/sts
  step3_create_pool
  rollback_step3_delete_pool      # только для отката, не часть штатного прогона

Пример: source T-0-8_step5a_federation_pool.sh && step1_check_allowed_policy_member_domains
EOF
}

if [[ "${1:-}" != "" ]]; then
  "$1"
else
  usage
fi
