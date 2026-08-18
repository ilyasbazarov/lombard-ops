"""
functions/cf_daily/bq_loader.py — T-1-0, шаг 1

Читает NDJSON-выгрузку таблицы `CONTRACTS` из GCS (уже выгружена агентом,
`T-0-8`, путь `agent/{дата}/CONTRACTS.ndjson`) и загружает ЧАСТИЧНЫЙ маппинг в
`lombard_ops.loans_raw` (`02_DATA_CONTRACTS.md` §3, «Ограничения» брифа T-1-0):

    CONTRACT_ID      -> contract_id
    CONTRACT_DATE    -> issue_date
    PLAN_CLOSE_DATE  -> due_date
    DEPOSIT_SUM ÷100 -> loan_amount

Остальные колонки `loans_raw` (vehicle_id, client_name, vehicle_make/model/year,
status_raw, renewed, renewed_date) требуют других таблиц (`SUBJECTS`,
`CUSTOM_FIELDS_VALUES`, `OPERATIONS`) — предмет `T-1-2`, здесь пишутся `NULL`
сознательно, не тихо.

Загрузка в BQ — явным списком колонок (`SchemaField`, не autodetect, `05 §II`).
Денежные величины в NDJSON — строкой (`connector/agent/agent.py:_json_safe`,
`decimal.Decimal` → `str`), даты — ISO-8601; повторного decode/charset этот
модуль не делает (`LOMBARD_DB_CHARSET` уже применён на этапе агента).
"""

from __future__ import annotations

import datetime
import decimal
import json
import logging
from typing import Any, Callable

logger = logging.getLogger("lombard.cf_daily.bq_loader")


class GcsPathError(ValueError):
    """`gs://` путь не разбирается на бакет и имя блоба."""


def parse_gs_path(gs_path: str) -> tuple[str, str]:
    if not gs_path.startswith("gs://"):
        raise GcsPathError(f"не gs:// путь: {gs_path}")
    rest = gs_path[len("gs://") :]
    if "/" not in rest:
        raise GcsPathError(f"нет имени блоба в пути: {gs_path}")
    bucket, blob_name = rest.split("/", 1)
    if not bucket or not blob_name:
        raise GcsPathError(f"пустой бакет или блоб в пути: {gs_path}")
    return bucket, blob_name


def _default_gcs_client_factory(project_id: str | None) -> Any:
    from google.cloud import storage  # type: ignore

    return storage.Client(project=project_id)


def read_ndjson_from_gcs(
    gs_path: str,
    *,
    project_id: str | None = None,
    client_factory: Callable[[str | None], Any] = _default_gcs_client_factory,
) -> list[dict]:
    """Скачивает объект `gs_path`, парсит построчный JSON. Пустые строки пропускаются."""
    bucket_name, blob_name = parse_gs_path(gs_path)
    client = client_factory(project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    text = blob.download_as_text()
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def map_contract_row(row: dict, *, loaded_at: datetime.datetime) -> dict:
    """Маппинг ОДНОЙ строки `CONTRACTS` -> `loans_raw`, частичный по правилу
    «Ограничения» брифа T-1-0 (не дефект — заполнены только колонки, выводимые
    из этой одной таблицы)."""
    deposit_sum = row.get("DEPOSIT_SUM")
    loan_amount = None
    if deposit_sum is not None:
        loan_amount = str(decimal.Decimal(str(deposit_sum)) / decimal.Decimal(100))
    return {
        "contract_id": str(row["CONTRACT_ID"]),
        "vehicle_id": None,
        "client_name": None,
        "vehicle_make": None,
        "vehicle_model": None,
        "vehicle_year": None,
        "loan_amount": loan_amount,
        "issue_date": row.get("CONTRACT_DATE"),
        "due_date": row.get("PLAN_CLOSE_DATE"),
        "status_raw": None,
        "renewed": None,
        "renewed_date": None,
        "loaded_at": loaded_at.isoformat(),
    }


# Явная схема `loans_raw` — источник истины `sql/ddl/lombard_ops.sql`, дословно.
LOANS_RAW_SCHEMA_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("contract_id", "STRING", "REQUIRED"),
    ("vehicle_id", "STRING", "NULLABLE"),
    ("client_name", "STRING", "NULLABLE"),
    ("vehicle_make", "STRING", "NULLABLE"),
    ("vehicle_model", "STRING", "NULLABLE"),
    ("vehicle_year", "INT64", "NULLABLE"),
    ("loan_amount", "NUMERIC", "NULLABLE"),
    ("issue_date", "DATE", "NULLABLE"),
    ("due_date", "DATE", "NULLABLE"),
    ("status_raw", "STRING", "NULLABLE"),
    ("renewed", "BOOL", "NULLABLE"),
    ("renewed_date", "DATE", "NULLABLE"),
    ("loaded_at", "TIMESTAMP", "REQUIRED"),
)


def _default_bq_client_factory(project_id: str | None) -> Any:
    from google.cloud import bigquery  # type: ignore

    return bigquery.Client(project=project_id)


def load_rows_to_bq(
    rows: list[dict],
    *,
    dataset: str = "lombard_ops",
    table: str = "loans_raw",
    project_id: str | None = None,
    client_factory: Callable[[str | None], Any] = _default_bq_client_factory,
) -> int:
    """Загружает список маппированных строк явным списком колонок
    (`SchemaField`, не autodetect — `05 §II`). Возвращает счёт загруженных строк."""
    from google.cloud import bigquery  # type: ignore

    schema = [
        bigquery.SchemaField(name, field_type, mode=mode)
        for name, field_type, mode in LOANS_RAW_SCHEMA_FIELDS
    ]
    client = client_factory(project_id)
    table_ref = f"{project_id}.{dataset}.{table}" if project_id else f"{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    job.result()
    logger.info("загружено %d строк в %s", len(rows), table_ref)
    return len(rows)


def load_contracts_blob(
    gs_path: str,
    *,
    project_id: str,
    now: datetime.datetime | None = None,
    gcs_client_factory: Callable[[str | None], Any] = _default_gcs_client_factory,
    bq_client_factory: Callable[[str | None], Any] = _default_bq_client_factory,
) -> tuple[int, datetime.datetime, list[dict]]:
    """Оркестрация шага 1: читает NDJSON из `gs_path`, маппит по правилу выше,
    загружает в `loans_raw`. Возвращает `(счёт строк, loaded_at, маппированные строки)`
    — маппированные строки нужны шагу 4 брифа (в) для выбора одного договора."""
    loaded_at = now or datetime.datetime.now(datetime.timezone.utc)
    raw_rows = read_ndjson_from_gcs(
        gs_path, project_id=project_id, client_factory=gcs_client_factory
    )
    mapped_rows = [map_contract_row(row, loaded_at=loaded_at) for row in raw_rows]
    count = load_rows_to_bq(
        mapped_rows, project_id=project_id, client_factory=bq_client_factory
    )
    return count, loaded_at, mapped_rows
