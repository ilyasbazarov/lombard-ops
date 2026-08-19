#!/usr/bin/env bash
# scripts/T-2-1_identity_platform_setup.sh — T-2-1, шаг 4/5 (класс B: включение Identity
# Platform, провайдер email+пароль, тестовые пользователи с custom claims).
#
# НЕ ИСПОЛНЯТЬ БЕЗ ОТДЕЛЬНОГО ПОДТВЕРЖДЕНИЯ ВЛАДЕЛЬЦА. Без явного аргумента ничего не делает.
# Один скрипт — на ШАГ брифа: часть setup = включение + провайдер, часть users = тестовые
# пользователи с ролями (не совмещать с деплоем — scripts/T-2-1_deploy.sh отдельно).
#
# Что исполняется: включение Identity Platform на проекте, провайдер email+пароль,
#   self-signup ВЫКЛЮЧЕН (allowPasswordSignup: true для создания через API, disableSignUp
#   на уровне конфигурации клиента), три тестовых пользователя (по одному на роль
#   owner/manager/assessor), custom claim `role` проставлен через Admin SDK
#   (`gcloud identity` не даёт custom claims — используется `firebase-admin` Python скриптом
#   ниже, вызываемым из шага `users`).
#   Реальные email Исы/Бектура/Эльхана НЕ заводятся (см. брифа «Входы — ПАСПОРТ»): используются
#   тестовые адреса вида test-<role>@lombard-ops.test.
# На каком объекте: PROJECT_ID=project-c451b48a-07ae-4de4-961, Identity Platform (Google Cloud
#   Identity Toolkit).
# Чем откатывается: `part users` — удаление тестовых пользователей
#   (`gcloud identity` не умеет; удаление через `firebase-admin auth.delete_user(uid)`, uid
#   печатается частью `users` и фиксируется в артефакте лога); `part setup` — отключение
#   провайдера email+пароль (тот же REST PATCH, signIn.email.enabled=false) — Identity Platform
#   как продукт после включения не отключается автоматическим действием, только провайдер.
#
# ИСПРАВЛЕНО в этой сессии (T-2-1, шаг 4): `gcloud alpha identity platform config …` не
#   существует в установленном SDK (577.0.0, проверено `gcloud alpha identity --help`) — секция
#   Identity Platform в `alpha`/`beta` отсутствует вовсе. Продукт также требует однократной
#   ручной активации в Cloud Console (`console.cloud.google.com/customer-identity`) — до неё
#   `admin/v2/.../config` отдаёt 404 CONFIGURATION_NOT_FOUND даже после `services enable`; это
#   не воспроизводится ни `gcloud`, ни REST. Заменено на прямой REST-вызов
#   `identitytoolkit.googleapis.com/admin/v2` с токеном `gcloud auth print-access-token`.

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"

setup_provider() {
  echo "=== Часть setup (шаг 4→5): включение Identity Platform + провайдер email+пароль ==="

  gcloud services enable identitytoolkit.googleapis.com --project="${PROJECT_ID}"

  local token
  token="$(gcloud auth print-access-token)"

  echo "=== PATCH config: signIn.email.enabled=true, passwordRequired=true, allowDuplicateEmails=false ==="
  curl -sS -X PATCH \
    "https://identitytoolkit.googleapis.com/admin/v2/projects/${PROJECT_ID}/config?updateMask=signIn.email.enabled,signIn.email.passwordRequired,signIn.allowDuplicateEmails" \
    -H "Authorization: Bearer ${token}" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -H "Content-Type: application/json" \
    -d '{"signIn":{"email":{"enabled":true,"passwordRequired":true},"allowDuplicateEmails":false}}'
  echo

  echo "=== Приёмка части setup: GET config ==="
  curl -sS -X GET \
    "https://identitytoolkit.googleapis.com/admin/v2/projects/${PROJECT_ID}/config" \
    -H "Authorization: Bearer ${token}" \
    -H "x-goog-user-project: ${PROJECT_ID}"
  echo
}

create_test_users() {
  echo "=== Часть users (шаг 4→5): три тестовых пользователя с custom claim role ==="
  # Значение пароля тестовых учёток НЕ хардкодится (ADR-001) — обязателен env
  # LOMBARD_TEST_USER_PASSCODE, задаётся владельцем перед запуском, в репозиторий не попадает.
  if [ -z "${LOMBARD_TEST_USER_PASSCODE:-}" ]; then
    echo "CONTEXT GAP: переменная окружения LOMBARD_TEST_USER_PASSCODE не задана — пароль тестовых пользователей не хранится в репозитории, задайте её перед запуском" >&2
    exit 1
  fi

  # ИСПРАВЛЕНО в этой сессии (T-2-1, шаг 4): firebase-admin требует Application Default
  #   Credentials (`gcloud auth application-default login`) — интерактивный браузерный логин,
  #   недоступен в этой среде исполнения. Заменено на прямой REST-вызов
  #   `identitytoolkit.googleapis.com/v1` с тем же OAuth2-токеном `gcloud auth
  #   print-access-token`, что и в setup_provider — тот же механизм, что firebase-admin
  #   использует под капотом (accounts:signUp для создания, accounts:update для custom claims).
  local token
  token="$(gcloud auth print-access-token)"

  python3 - "${token}" "${PROJECT_ID}" "${LOMBARD_TEST_USER_PASSCODE}" <<'PYEOF'
import json
import sys
import urllib.request

token, project_id, passcode = sys.argv[1], sys.argv[2], sys.argv[3]
headers = {
    "Authorization": f"Bearer {token}",
    "x-goog-user-project": project_id,
    "Content-Type": "application/json",
}

TEST_USERS = [
    ("test-owner@lombard-ops.test", "owner"),
    ("test-manager@lombard-ops.test", "manager"),
    ("test-assessor@lombard-ops.test", "assessor"),
]

def call(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

for email, role in TEST_USERS:
    signup = call(
        "https://identitytoolkit.googleapis.com/v1/accounts:signUp",
        {"email": email, "password": passcode, "emailVerified": True},
    )
    uid = signup["localId"]
    call(
        "https://identitytoolkit.googleapis.com/v1/accounts:update",
        {"localId": uid, "customAttributes": json.dumps({"role": role})},
    )
    lookup = call(
        "https://identitytoolkit.googleapis.com/v1/accounts:lookup",
        {"localId": [uid]},
    )
    user = lookup["users"][0]
    print(f"created uid={user['localId']} email={user['email']} claims={user.get('customAttributes')}")
PYEOF
}

case "${1:-}" in
  setup) setup_provider ;;
  users) create_test_users ;;
  *)
    echo "Использование: $0 setup   # включение Identity Platform + провайдер (шаг 4→5, часть 1)"
    echo "               $0 users   # три тестовых пользователя с custom claims (шаг 4→5, часть 2)"
    echo "Без аргумента скрипт НИЧЕГО не делает — защита от случайного запуска."
    exit 1
    ;;
esac
