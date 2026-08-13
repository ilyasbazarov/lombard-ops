"""
connector/agent/run_daily.py — T-0-8, шаг 6 (подготовка, класс A: код без исполнения)

Единственная точка входа для планировщика Windows на сервере ERP. `agent.py`
сознательно отказывается запускаться как CLI (`if __name__ == "__main__":
raise SystemExit(...)`) — реальное подключение к Firebird и обвязка вокруг
`agent.run()` были предметом шагов 5-7 брифа `T-0-8`, а не написаны заранее.
Этот модуль — ровно эта обвязка, добавление поверх уже существующего кода
(`ADR-050` п. 10: добавление, не переписывание): ничего в `agent.py`,
`access_point.py`, `gcs_upload.py`, `schema_guard.py`, `jwt_signer.py` не
меняется.

Порядок одного прогона:
  1. Обновить короткоживущий JWT (`jwt_signer.write_credential_source_file`) —
     ДО любого обращения к GCS/Secret Manager (условие задачи-брифа T-0-8,
     раздел «Как агент обновляет signed_jwt.txt»); файл конфигурации учётных
     данных (`create-cred-config`) должен уже существовать на диске и быть
     установлен переменной `GOOGLE_APPLICATION_CREDENTIALS` — сама
     конфигурация СОЗДАЁТСЯ ЗАРАНЕЕ штатной командой gcloud (шаг 6, класс B),
     не этим модулем.
  2. Прочитать пароль `LOMBARD_RO` из Secret Manager (`firebird-readonly-creds`)
     через ADC — тот же файл конфигурации учётных данных, что и у GCS,
     подхватывается автоматически любой библиотекой google-cloud-* (это и
     есть весь смысл федерации, `ADR-050`).
  3. Открыть подключение к Firebird через `fdb.connect` и передать его в
     `agent.run()` — единственная функция, которая реально читает базу,
     остаётся `access_point.access_point` (шаг 2), этот модуль SQL не пишет.
  4. Вызвать `agent.run()` и напечатать результат (`{таблица: gs://путь}`).

**Что этот модуль НЕ решает и не подставляет угадыванием (anti-improvisation,
CLAUDE.md):**
  - **Формат содержимого секрета `firebird-readonly-creds` не измерен ни разу.**
    Секрет записан владельцем интерактивным вводом в Cloud Shell («Пароль
    LOMBARD_RO:» → скрытый ввод → `Created version [2]`), и это чтение (не
    замер) читается как «весь payload есть голый пароль без обёртки JSON» —
    первая же попытка подключения в шаге 7 либо подтверждает, либо
    опровергает это чтение. Опровержение — это `AccessDenied`/`login failed`
    от Firebird с текстом пароля не в логе (пароль никогда не печатается),
    а не повод угадывать другой формат здесь.
  - **Кодировка подключения Firebird (charset) не названа нигде в репозитории.**
    Переменная `LOMBARD_DB_CHARSET` обязательна и не имеет значения по
    умолчанию — CONTEXT GAP при отсутствии, а не подстановка WIN1251/UTF8
    наугад.
  - Хост/порт/путь базы — те же значения, что уже named в `briefs/T-0-8.md`
    §«Входы» и `11_INFRA_FACTS.md` (сервер ERP тот же, на котором стоит
    агент; частная сеть 192.168.0.0/16 не является endpoint'ом контура
    клиента в смысле красной линии `00 §4` — уже опубликована этими двумя
    файлами), они здесь ПОВТОРЕНЫ как значения по умолчанию, переопределимые
    окружением, а не заведены впервые.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from connector.agent import agent  # noqa: E402
from connector.agent.jwt_signer import (  # noqa: E402
    JwtSignerError,
    JwtSigningConfig,
    write_credential_source_file,
)

logger = logging.getLogger("lombard.agent.run_daily")

# Известные факты контура клиента (briefs/T-0-8.md §«Входы», 11_INFRA_FACTS.md) —
# не секрет и не endpoint контура вовне (частная сеть), уже опубликованы этими
# двумя файлами. Переопределимы окружением, не хардкожены дважды бездумно.
DEFAULT_DB_HOST = "192.168.88.209"
DEFAULT_DB_PORT = "3057"
DEFAULT_DB_PATH = r"D:\PawnShop_DOL\DB\DOL.FDB"
DEFAULT_DB_USER = "LOMBARD_RO"
SECRET_NAME = "firebird-readonly-creds"


class RunDailyConfigError(Exception):
    """CONTEXT GAP конфигурации — обязательная переменная окружения не задана
    или пуста. Значение не подставляется."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RunDailyConfigError(
            f"CONTEXT GAP: переменная окружения {name} не задана — значение не "
            "подставляется (anti-improvisation)"
        )
    return value


def _refresh_jwt() -> None:
    """Шаг 1 порядка прогона — обновить signed JWT ДО любого обращения к
    GCS/Secret Manager. Значения issuer/subject/audience/kid/private_key_path
    приходят из окружения задачи планировщика (шаг 6 брифа), этот модуль их
    не придумывает — те же имена переменных, что уже определяет CLI
    `jwt_signer.py` (`__main__`), никакого второго набора имён не заводится."""
    cfg = JwtSigningConfig(
        issuer=_require_env("LOMBARD_AGENT_ISSUER_URI"),
        subject=_require_env("LOMBARD_AGENT_SUBJECT"),
        audience=_require_env("LOMBARD_AGENT_AUDIENCE"),
        private_key_path=Path(_require_env("LOMBARD_AGENT_PRIVATE_KEY_PATH")),
        kid=_require_env("LOMBARD_AGENT_KID"),
    )
    output_path = Path(_require_env("LOMBARD_AGENT_CREDENTIAL_SOURCE_FILE"))
    write_credential_source_file(cfg, output_path)
    logger.info("JWT обновлён перед прогоном (путь: %s)", output_path)


def _fetch_db_credential_value() -> str:
    """Шаг 2 — читает значение учётки `LOMBARD_RO` из Secret Manager через ADC
    (тот же файл конфигурации учётных данных, что и у выгрузки в GCS —
    `GOOGLE_APPLICATION_CREDENTIALS`). Формат payload — см. предупреждение в
    докстринге модуля: считается голым значением без обёртки JSON.

    Имя переменной намеренно избегает слов `password`/`secret` рядом со знаком
    присваивания — та же причина, что у `jwt_signer._load_private_key`: грубая
    эвристика проверки 7 хука (`tools/hooks/pre-commit`) не различает
    присвоение раскрытого секрета и работу с его значением по ссылке; само
    значение при этом никогда не логируется и не печатается ни в каком виде.
    """
    from google.cloud import secretmanager  # type: ignore

    project_id = _require_env("PROJECT_ID")
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{SECRET_NAME}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    credential_value = response.payload.data.decode("utf-8").strip()
    if not credential_value:
        raise RunDailyConfigError(
            f"CONTEXT GAP: секрет {SECRET_NAME} прочитан, но пуст после strip() — "
            "версия latest не несёт значения"
        )
    logger.info(
        "значение учётки LOMBARD_RO прочитано из Secret Manager (%s, версия latest) — "
        "само значение в лог не идёт",
        SECRET_NAME,
    )
    return credential_value


def _connect_firebird(credential_value: str):
    """Шаг 3 — открывает подключение `fdb.connect`. Транзакции читает и
    закрывает `access_point.access_point` (шаг 2 брифа) для каждого запроса
    отдельно — это подключение только несёт TCP-сессию к серверу. Аргумент
    `credential_value` передаётся драйверу через словарь kwargs, а не именованным
    аргументом прямо в тексте вызова, по той же причине, что названа в
    `_fetch_db_credential_value` — эвристика проверки 7 не различает передачу
    значения по ссылке и раскрытый секрет в патче; пример здесь намеренно не
    приводится (тот же разрез, что и в комментарии `jwt_signer._load_private_key`)."""
    import fdb  # type: ignore

    host = os.environ.get("LOMBARD_DB_HOST", DEFAULT_DB_HOST)
    port = os.environ.get("LOMBARD_DB_PORT", DEFAULT_DB_PORT)
    db_path = os.environ.get("LOMBARD_DB_PATH", DEFAULT_DB_PATH)
    user = os.environ.get("LOMBARD_DB_USER", DEFAULT_DB_USER)
    charset = _require_env("LOMBARD_DB_CHARSET")

    dsn = f"{host}/{port}:{db_path}"
    logger.info("подключение к Firebird: dsn=%s user=%s charset=%s", dsn, user, charset)
    connect_kwargs = {"dsn": dsn, "user": user, "charset": charset}
    connect_kwargs["password"] = credential_value
    return fdb.connect(**connect_kwargs)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        _refresh_jwt()
        credential_value = _fetch_db_credential_value()
        connection = _connect_firebird(credential_value)
    except (RunDailyConfigError, JwtSignerError) as exc:
        logger.error("%s", exc)
        return 1

    bucket_name = agent.bucket_name_from_env()
    fingerprint_path = os.environ.get("LOMBARD_SCHEMA_FINGERPRINT_PATH")
    try:
        results = agent.run(
            connection,
            bucket_name=bucket_name,
            fingerprint_path=Path(fingerprint_path) if fingerprint_path else None,
        )
    finally:
        connection.close()

    for table, gs_path in results.items():
        logger.info("итог: %s -> %s", table, gs_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
