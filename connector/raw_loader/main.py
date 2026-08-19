"""
connector/raw_loader/main.py — T-1-1, шаг 5

Точка входа Cloud Run Job `raw-loader` (обычный Python-скрипт, Cloud Run Jobs
не несёт HTTP-триггера в отличие от Cloud Function `cf-daily`).

Порядок (дословно шаг 5 брифа `briefs/T-1-1.md`):
  (а) прочитать `connector/mapping.json`, построить ожидаемые схемы девяти
      таблиц (тот же генератор шага 1 — `connector.generate_raw_ddl`, логика
      построения схемы не дублируется);
  (б) для каждой из девяти таблиц — найти самый свежий блоб
      `agent/<дата>/<TABLE>.ndjson` в бакете `${PROJECT_ID}-cfsource`
      (листинг префикса `agent/`, максимум по имени даты, тот же приём, что
      `functions/cf_daily/main.py:find_latest_contracts_blob`, обобщённый на
      переменное имя таблицы);
  (в) вызвать guard (шаг 2) для этой таблицы; расхождение → залогировать
      причину, прочитать секреты, отправить алерт, ОСТАНОВИТЬ ВЕСЬ ПРОГОН;
  (г) guard прошёл → вызвать загрузчик (шаг 3), залогировать счёт строк и
      `loaded_at`;
  (д) после всех девяти, если ни одного расхождения не было — сводная строка,
      код `0`.

**Решение исполнителя (шаг 5 брифа, зафиксировано здесь и в артефакте
`reference/T-1-1_raw_loader_run_2026-08-19.md`): любой упавший шаг ОСТАНАВЛИВАЕТ
ВЕСЬ ПРОГОН, не только guard-расхождение.** Тот же принцип, что «Ретраев эта
задача не проектирует» (`T-1-0`, «Ограничения»): один прогон, один проход по
девяти таблицам, первый отказ (транспортный — GCS/BQ/сеть, или guard) стопит
остальное и ждёт следующих суток, а не продолжает частичной загрузкой. Причина
выбора: девять `raw_*` — источник единственного слоя канонизации `T-1-2`;
частичный прогон (восемь из девяти свежих, одна вчерашняя) создаёт скрытую
рассинхронизацию дат между таблицами слоя сырья, которую canonical-слой не
видит и не может обнаружить сам — дешевле подождать целые сутки, чем
диагностировать разъехавшийся `loaded_at` по колонкам таблиц позже.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

# Импорты ФЛАТ (не `connector.raw_loader.xxx`, не `connector.xxx`): деплой
# идёт `--source=connector/raw_loader` (шаг 8 брифа), контейнер получает
# СОДЕРЖИМОЕ этого каталога корнем — импорт из каталога вне `--source`
# неразрешим (ADR-078 пп.4-5, тот же дефект стоил раунда деплоя `cf-daily`).
# По этой же причине `generate_raw_ddl.py` и `mapping.json` — КОПИИ файлов
# `connector/generate_raw_ddl.py`/`connector/mapping.json` внутри этого
# каталога, тем же приёмом, что `telegram_send.py` (копия, не импорт
# межпакетно). Источник истины остаётся `connector/mapping.json` —
# `scripts/T-1-1_deploy.sh` обновляет обе копии байт-в-байт непосредственно
# перед деплоем, расхождение копий проверяется тестом (`test_main.py`).
from generate_raw_ddl import (
    load_schema_fingerprint,
    raw_table_name,
    table_schema_fields,
)
from guard import (
    SchemaLoadGuardMismatch,
    _default_bq_client_factory,
    check_schema,
)
from loader import (
    _default_gcs_client_factory,
    load_table_blob,
)
from telegram_send import send_message

logger = logging.getLogger("lombard.raw_loader.main")

MAPPING_PATH = Path(__file__).resolve().parent / "mapping.json"


class RawLoaderStepError(RuntimeError):
    """Один из шагов прогона упал (guard, GCS, BQ, сеть) — несёт имя таблицы
    и причину; прогон останавливается целиком (см. докстринг модуля)."""

    def __init__(self, table: str, cause: Exception | str):
        self.table = table
        self.cause = cause
        super().__init__(f"таблица {table}: {cause}")


def _default_storage_client_factory(project_id: str | None) -> Any:
    from google.cloud import storage  # type: ignore

    return storage.Client(project=project_id)


def find_latest_table_blob(
    bucket_name: str,
    table: str,
    *,
    project_id: str | None = None,
    client_factory: Callable[[str | None], Any] = _default_storage_client_factory,
) -> str:
    """Листинг префикса `agent/` в бакете, выбор МАКСИМАЛЬНОЙ по имени даты
    каталога (лексикографический порядок = хронологический), путь до
    `<TABLE>.ndjson` внутри — обобщение
    `functions/cf_daily/main.py:find_latest_contracts_blob` на переменную
    таблицу. Дата не хардкодится нигде в этой функции."""
    client = client_factory(project_id)
    iterator = client.list_blobs(bucket_name, prefix="agent/", delimiter="/")
    list(iterator)  # обязателен для заполнения .prefixes у клиента GCS
    prefixes = sorted(iterator.prefixes)
    if not prefixes:
        raise RuntimeError(
            f"в бакете {bucket_name} нет ни одного каталога agent/<дата>/ — "
            "выгрузки агента (T-0-8) не найдено"
        )
    latest_prefix = prefixes[-1]  # например 'agent/2026-08-19/'
    return f"gs://{bucket_name}/{latest_prefix}{table}.ndjson"


def _default_secret_client_factory() -> Any:
    from google.cloud import secretmanager  # type: ignore

    return secretmanager.SecretManagerServiceClient()


def read_secret(
    project_id: str,
    secret_id: str,
    *,
    version: str = "latest",
    client_factory: Callable[[], Any] = _default_secret_client_factory,
) -> str:
    client = client_factory()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("utf-8")


def send_alert(
    project_id: str,
    text: str,
    *,
    secret_client_factory: Callable[[], Any] = _default_secret_client_factory,
    http_post: Callable[[str, bytes], dict] | None = None,
) -> str:
    """Читает `telegram-bot-token`/`chat_id` (ключ `owner`) из Secret Manager
    и отправляет одно сообщение (`send_message`, без ретраев — тот же принцип,
    что `T-1-0`). Возвращает `message_id`."""
    bot_token_value = read_secret(
        project_id, "telegram-bot-token", client_factory=secret_client_factory
    )
    chat_id_raw = read_secret(project_id, "chat_id", client_factory=secret_client_factory)
    chat_id = json.loads(chat_id_raw)["owner"]
    kwargs: dict[str, Any] = {}
    if http_post is not None:
        kwargs["http_post"] = http_post
    return send_message(bot_token_value, str(chat_id), text, **kwargs)


def run_pipeline(
    *,
    project_id: str,
    bucket_name: str,
    dataset: str = "lombard_ops",
    mapping_path: Any = MAPPING_PATH,
    now: datetime.datetime | None = None,
    storage_client_factory: Callable[[str | None], Any] = _default_storage_client_factory,
    gcs_client_factory: Callable[[str | None], Any] = _default_gcs_client_factory,
    bq_client_factory: Callable[[str | None], Any] = _default_bq_client_factory,
    secret_client_factory: Callable[[], Any] = _default_secret_client_factory,
    http_post: Callable[[str, bytes], dict] | None = None,
) -> dict[str, dict[str, Any]]:
    """Оркестрация шагов (а)-(д). Любой отказ (guard-расхождение или
    транспортный) поднимает `RawLoaderStepError` и останавливает прогон
    целиком — решение исполнителя, см. докстринг модуля. Возвращает
    `{table: {"row_count": int, "loaded_at": iso}}` по всем девяти при успехе."""
    now = now or datetime.datetime.now(datetime.timezone.utc)

    fingerprint = load_schema_fingerprint(mapping_path)
    results: dict[str, dict[str, Any]] = {}

    for table, columns in fingerprint.items():
        expected_schema = table_schema_fields(table, columns)
        bq_table = raw_table_name(table)

        try:
            gs_path = find_latest_table_blob(
                bucket_name, table, project_id=project_id, client_factory=storage_client_factory
            )
        except Exception as exc:  # noqa: BLE001
            raise RawLoaderStepError(table, f"поиск свежего блоба: {exc}") from exc

        try:
            check_schema(
                bq_table,
                expected_schema,
                dataset=dataset,
                project_id=project_id,
                client_factory=bq_client_factory,
            )
        except SchemaLoadGuardMismatch as exc:
            logger.error("GUARD ОСТАНОВИЛ ПРОГОН на таблице %s: %s", table, exc)
            alert_kwargs: dict[str, Any] = {"secret_client_factory": secret_client_factory}
            if http_post is not None:
                alert_kwargs["http_post"] = http_post
            send_alert(
                project_id,
                f"raw-loader: guard схемы остановил прогон на таблице {bq_table}: {exc}",
                **alert_kwargs,
            )
            raise RawLoaderStepError(table, exc) from exc
        except Exception as exc:  # noqa: BLE001 — транспортный отказ guard'а (BQ недоступен)
            raise RawLoaderStepError(table, f"guard: {exc}") from exc

        try:
            count, loaded_at = load_table_blob(
                gs_path,
                table=bq_table,
                expected_schema=expected_schema,
                project_id=project_id,
                dataset=dataset,
                now=now,
                gcs_client_factory=gcs_client_factory,
                bq_client_factory=bq_client_factory,
            )
        except Exception as exc:  # noqa: BLE001
            raise RawLoaderStepError(table, f"загрузка: {exc}") from exc

        logger.info(
            "(г) %s: загружено %d строк, loaded_at=%s, source=%s",
            bq_table,
            count,
            loaded_at.isoformat(),
            gs_path,
        )
        results[table] = {"row_count": count, "loaded_at": loaded_at.isoformat()}

    logger.info(
        "(д) сводка: %d таблиц загружено без расхождений — %s",
        len(results),
        {t: r["row_count"] for t, r in results.items()},
    )
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        print(
            "CONTEXT GAP: переменная окружения PROJECT_ID не задана — имя бакета "
            "и project_id BigQuery/Secret Manager построить не из чего"
        )
        return 1
    bucket_name = f"{project_id}-cfsource"

    try:
        run_pipeline(project_id=project_id, bucket_name=bucket_name)
    except RawLoaderStepError as exc:
        logger.error("ПРОГОН ОСТАНОВЛЕН на таблице %s: %s", exc.table, exc.cause)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
