"""
functions/cf_daily/main.py — T-1-0, шаг 4

Точка входа Cloud Function Gen2 HTTP-триггер `cf-daily` (деплой — карточка
подтверждения 1, шаг 6 брифа, класс B; этот файл — код класса A).

Порядок (дословно шаг 4 брифа `briefs/T-1-0.md`):
  (а) найти самый свежий блоб `agent/<дата>/CONTRACTS.ndjson` в бакете
      `${PROJECT_ID}-cfsource` — листинг префикса `agent/`, дата не хардкодится;
  (б) вызвать `bq_loader`, залогировать счёт загруженных строк и `loaded_at`;
  (в) выбрать ОДИН договор из загруженных — правило выбора исполнителя: первый
      по возрастанию `contract_id` с непустым `due_date`;
  (г) вызвать `status.compute_status`;
  (д) прочитать `telegram-bot-token` и `chat_id` (ключ `owner`) из Secret
      Manager, вызвать `telegram_send`;
  (е) вернуть HTTP 200 с телом, печатающим три факта — счёт строк, вычисленный
      статус, `message_id`.

Любой шаг (а)–(д) упал → HTTP 500 с текстом причины, не тихий 200.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any, Callable

from functions.cf_daily import bq_loader, status, telegram_send

logger = logging.getLogger("lombard.cf_daily.main")


class PipelineError(RuntimeError):
    """Один из шагов (а)–(д) конвейера упал — несёт имя упавшего шага и причину."""

    def __init__(self, step: str, cause: Exception):
        self.step = step
        self.cause = cause
        super().__init__(f"шаг ({step}) конвейера cf-daily упал: {cause}")


def _default_storage_client_factory(project_id: str | None) -> Any:
    from google.cloud import storage  # type: ignore

    return storage.Client(project=project_id)


def find_latest_contracts_blob(
    bucket_name: str,
    *,
    project_id: str | None = None,
    client_factory: Callable[[str | None], Any] = _default_storage_client_factory,
) -> str:
    """Листинг префикса `agent/` в бакете, выбор МАКСИМАЛЬНОЙ по имени даты
    каталога (даты в имени `YYYY-MM-DD` — лексикографический порядок совпадает
    с хронологическим). Дата не хардкодится нигде в этой функции."""
    client = client_factory(project_id)
    iterator = client.list_blobs(bucket_name, prefix="agent/", delimiter="/")
    list(iterator)  # обязателен для заполнения .prefixes у клиента GCS
    prefixes = sorted(iterator.prefixes)
    if not prefixes:
        raise RuntimeError(
            f"в бакете {bucket_name} нет ни одного каталога agent/<дата>/ — "
            "выгрузки агента (T-0-8) не найдено"
        )
    latest_prefix = prefixes[-1]  # например 'agent/2026-08-17/'
    return f"gs://{bucket_name}/{latest_prefix}CONTRACTS.ndjson"


def select_one_contract(mapped_rows: list[dict]) -> dict:
    """Правило выбора (решение исполнителя, зафиксировано в артефакте замера):
    первый по возрастанию `contract_id` с непустым `due_date`."""
    candidates = [row for row in mapped_rows if row.get("due_date")]
    if not candidates:
        raise RuntimeError(
            "ни одна из загруженных строк не несёт непустой due_date — выбрать "
            "договор для статуса не из чего"
        )
    return min(candidates, key=lambda row: int(row["contract_id"]))


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


def run_pipeline(
    *,
    project_id: str,
    bucket_name: str,
    today: datetime.date | None = None,
    storage_client_factory: Callable[[str | None], Any] = _default_storage_client_factory,
    gcs_client_factory: Callable[[str | None], Any] = _default_storage_client_factory,
    bq_client_factory: Callable[[str | None], Any] = bq_loader._default_bq_client_factory,
    secret_client_factory: Callable[[], Any] = _default_secret_client_factory,
    http_post: Callable[[str, bytes], dict] = telegram_send._default_http_post,
) -> dict:
    """Оркестрация шагов (а)–(е). Поднимает `PipelineError` на первом упавшем
    шаге с его именем — вызывающий код (`cf_daily`) превращает это в HTTP 500."""
    today = today or datetime.datetime.now(datetime.timezone.utc).date()

    try:
        gs_path = find_latest_contracts_blob(
            bucket_name, project_id=project_id, client_factory=storage_client_factory
        )
    except Exception as exc:  # noqa: BLE001 — любая причина шага (а)
        raise PipelineError("а: поиск свежего блоба CONTRACTS.ndjson", exc) from exc

    try:
        row_count, loaded_at, mapped_rows = bq_loader.load_contracts_blob(
            gs_path,
            project_id=project_id,
            now=datetime.datetime.now(datetime.timezone.utc),
            gcs_client_factory=gcs_client_factory,
            bq_client_factory=bq_client_factory,
        )
        logger.info("(б) загружено %d строк, loaded_at=%s", row_count, loaded_at.isoformat())
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("б: загрузчик BQ", exc) from exc

    try:
        contract = select_one_contract(mapped_rows)
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("в: выбор одного договора", exc) from exc

    try:
        due_date = datetime.date.fromisoformat(contract["due_date"])
        status_label, notify_roles = status.compute_status(due_date, today)
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("г: расчёт статуса", exc) from exc

    try:
        bot_token_value = read_secret(
            project_id, "telegram-bot-token", client_factory=secret_client_factory
        )
        chat_id_raw = read_secret(project_id, "chat_id", client_factory=secret_client_factory)
        chat_id = json.loads(chat_id_raw)["owner"]
        text = (
            f"Договор {contract['contract_id']}: статус {status_label}, "
            f"плановая дата закрытия {contract['due_date']}"
        )
        message_id = telegram_send.send_message(
            bot_token_value, str(chat_id), text, http_post=http_post
        )
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("д: отправка в Telegram", exc) from exc

    return {
        "row_count": row_count,
        "loaded_at": loaded_at.isoformat(),
        "contract_id": contract["contract_id"],
        "status": status_label,
        "notify_roles": list(notify_roles),
        "message_id": message_id,
    }


def cf_daily(request: Any) -> tuple[str, int]:
    """Сигнатура Cloud Functions Gen2 `functions_framework.http`."""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        return (
            json.dumps({"error": "CONTEXT GAP: переменная окружения PROJECT_ID не задана"}),
            500,
        )
    bucket_name = f"{project_id}-cfsource"

    try:
        result = run_pipeline(project_id=project_id, bucket_name=bucket_name)
    except PipelineError as exc:
        logger.error(str(exc))
        return json.dumps({"error": str(exc), "step": exc.step}), 500

    return json.dumps(result, ensure_ascii=False), 200
