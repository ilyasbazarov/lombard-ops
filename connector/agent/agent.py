"""
connector/agent/agent.py — T-0-8, шаг 4

Оркестрация: guard схемы перед чтением (`schema_guard`) → чтение девяти
разрешённых таблиц явными списками колонок через единственную точку доступа
(`access_point`) → сериализация построчно в NDJSON → выгрузка в GCS с повтором и
локальным журналом при недоступности (`gcs_upload`).

Список из девяти таблиц — `briefs/T-0-5.md` §«Список таблиц» (тот же список, что и
белый список `access_point.ALLOWED_TABLES`; оба обязаны совпадать, проверяется тестом
модуля). Бакет выгрузки — `${PROJECT_ID}-cfsource`, имя из `11_INFRA_FACTS.md`
(создан `T-0-7`); `PROJECT_ID` подставляется из окружения агента, не хардкодится
значением из публичного репозитория дважды.

Подключение к Firebird и ключ сервисного аккаунта GCP — это секреты контура клиента
и Secret Manager (`00 §4`, `05 §II`): они читаются из окружения/Secret Manager при
запуске службы (заводится шагами 5–6 брифа, класс B), а не лежат в этом файле.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

from connector.agent.access_point import ALLOWED_TABLES, access_point
from connector.agent.gcs_upload import RetryPolicy, upload_bytes
from connector.agent.schema_guard import (
    SchemaGuardMismatch,
    column_names,
    fingerprint_table,
    guard_check,
)

logger = logging.getLogger("lombard.agent")

# Девять таблиц брифа `T-0-5` — тот же набор, что и белый список `access_point`.
# Заведено списком, а не производной ALLOWED_TABLES, чтобы порядок чтения был
# детерминирован (frozenset порядка не гарантирует); совпадение множеств с
# ALLOWED_TABLES проверяется при импорте модуля, а не предполагается.
TABLES_TO_EXTRACT: tuple[str, ...] = (
    "CONTRACTS",
    "CONTRACTS_TERMS",
    "SUBJECTS",
    "CUSTOM_FIELDS_VALUES",
    "DIR_CUSTOM_FIELDS",
    "TABLES_TABLE",
    "CONTRACT_STATES",
    "DEPOSIT_TYPES",
    "OPERATIONS",
)

if set(TABLES_TO_EXTRACT) != ALLOWED_TABLES:
    raise SystemExit(
        "CONTEXT GAP: TABLES_TO_EXTRACT (agent.py) и ALLOWED_TABLES (access_point.py) "
        f"разошлись — только тут: {set(TABLES_TO_EXTRACT) - ALLOWED_TABLES}, "
        f"только там: {ALLOWED_TABLES - set(TABLES_TO_EXTRACT)}"
    )


def _serialize_ndjson(columns: list[str], rows: list[tuple]) -> bytes:
    lines = []
    for row in rows:
        record = {col: _json_safe(val) for col, val in zip(columns, row)}
        lines.append(json.dumps(record, ensure_ascii=False))
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def extract_table(connection: Any, table: str, columns: list[str]) -> tuple[list[str], list[tuple]]:
    """Читает таблицу явным списком колонок (список пришёл из отпечатка guard схемы,
    не придуман) через `access_point` — единственный путь SQL к базе."""
    col_list = ", ".join(columns)
    sql = f"SELECT {col_list} FROM {table}"
    rows = access_point(connection, sql)
    logger.info("прочитано %d строк из %s", len(rows), table)
    return columns, rows


def run(
    connection: Any,
    *,
    bucket_name: str,
    run_date: datetime.date | None = None,
    fingerprint_path: Path | None = None,
    upload_policy: RetryPolicy = RetryPolicy(),
) -> dict[str, str]:
    """Один прогон агента: guard → чтение девяти таблиц → выгрузка каждой отдельным
    NDJSON-объектом в GCS. Возвращает `{таблица: gs://путь}` для успешно
    загруженных; неудачные подняты исключением `UploadFailedPersisted` (объект при
    этом не теряется — лежит в локальном журнале, `gcs_upload.py`)."""
    run_date = run_date or datetime.date.today()

    guard_kwargs: dict[str, Any] = {}
    if fingerprint_path is not None:
        guard_kwargs["path"] = fingerprint_path

    try:
        guard_check(connection, list(TABLES_TO_EXTRACT), **guard_kwargs)
    except SchemaGuardMismatch:
        logger.error(
            "GUARD ОСТАНОВИЛ ПРОГОН: расхождение отпечатка схемы — чтение НЕ выполняется "
            "ни для одной таблицы (00 §3-БИС(c): стоп и алерт, не искажение)"
        )
        raise

    results: dict[str, str] = {}
    for table in TABLES_TO_EXTRACT:
        fp = fingerprint_table(connection, table)
        cols = column_names(fp)
        columns, rows = extract_table(connection, table, cols)
        payload = _serialize_ndjson(columns, rows)
        blob_name = f"agent/{run_date.isoformat()}/{table}.ndjson"
        gs_path = upload_bytes(bucket_name, blob_name, payload, policy=upload_policy)
        results[table] = gs_path
        logger.info("выгрузка %s: %d строк -> %s", table, len(rows), gs_path)

    return results


def bucket_name_from_env() -> str:
    """Имя бакета строится из `PROJECT_ID` окружения агента — сам `PROJECT_ID`
    берётся из переменной среды, установленной при развёртывании службы (шаг 6
    брифа), а не хардкодится второй раз поверх `11_INFRA_FACTS.md`."""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        raise SystemExit(
            "CONTEXT GAP: переменная окружения PROJECT_ID не задана — имя бакета "
            "${PROJECT_ID}-cfsource построить не из чего"
        )
    return f"{project_id}-cfsource"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(
        "CONTEXT GAP: запуск агента как службы — предмет шагов 5-7 брифа T-0-8 "
        "(класс B, сервер и облако клиента), не этого модуля. Этот файл — код для "
        "класса A; исполнение согласуется отдельной карточкой подтверждения."
    )
