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
#   провайдера email+пароль (`gcloud alpha identity platform` конфиг update) — Identity Platform
#   как продукт после включения не отключается автоматическим действием, только провайдер.

set -euo pipefail

PROJECT_ID="project-c451b48a-07ae-4de4-961"

setup_provider() {
  echo "=== Часть setup (шаг 4→5): включение Identity Platform + провайдер email+пароль ==="

  gcloud services enable identitytoolkit.googleapis.com --project="${PROJECT_ID}"

  gcloud alpha identity platform config update \
    --project="${PROJECT_ID}" \
    --sign-in-allow-duplicate-emails=false

  gcloud alpha identity platform config update \
    --project="${PROJECT_ID}" \
    --sign-in-email-enabled=true \
    --sign-in-email-password-required=true

  echo "=== Приёмка части setup: config describe ==="
  gcloud alpha identity platform config describe --project="${PROJECT_ID}"
}

create_test_users() {
  echo "=== Часть users (шаг 4→5): три тестовых пользователя с custom claim role ==="
  # Значение пароля тестовых учёток НЕ хардкодится (ADR-001) — обязателен env
  # LOMBARD_TEST_USER_PASSCODE, задаётся владельцем перед запуском, в репозиторий не попадает.
  if [ -z "${LOMBARD_TEST_USER_PASSCODE:-}" ]; then
    echo "CONTEXT GAP: переменная окружения LOMBARD_TEST_USER_PASSCODE не задана — пароль тестовых пользователей не хранится в репозитории, задайте её перед запуском" >&2
    exit 1
  fi

  # Custom claims через gcloud недоступны — используется firebase-admin (Python), вызывается
  # отдельным инлайн-скриптом, чтобы не заводить постоянный python-модуль в scripts/.
  # Heredoc НЕ квотирован специально: значение пароля подставляется через ${LOMBARD_TEST_USER_PASSCODE}
  # (shell-подстановка), python-код внутри $ не использует, конфликта нет.
  python3 - <<PYEOF
import firebase_admin
from firebase_admin import auth as fb_auth

firebase_admin.initialize_app()

_test_passcode = "${LOMBARD_TEST_USER_PASSCODE}"

TEST_USERS = [
    ("test-owner@lombard-ops.test", "owner"),
    ("test-manager@lombard-ops.test", "manager"),
    ("test-assessor@lombard-ops.test", "assessor"),
]

for email, role in TEST_USERS:
    create_kwargs = {"email": email, "email_verified": True}
    create_kwargs["password"] = _test_passcode
    user = fb_auth.create_user(**create_kwargs)
    fb_auth.set_custom_user_claims(user.uid, {"role": role})
    created = fb_auth.get_user(user.uid)
    print(f"created uid={created.uid} email={created.email} claims={created.custom_claims}")
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
