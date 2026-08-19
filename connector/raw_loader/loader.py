"""
connector/raw_loader/loader.py — T-1-1, шаг 3

Обобщение `functions/cf_daily/bq_loader.read_ndjson_from_gcs`/`load_rows_to_bq`
на произвольную таблицу слоя сырья: читает один блоб NDJSON из GCS, добавляет
`loaded_at` (момент запуска, UTC) и `source_blob` (путь блоба) КАЖДОЙ строке,
загружает явным списком колонок (`bigquery.LoadJobConfig`,
`source_format=NEWLINE_DELIMITED_JSON`, `write_disposition=WRITE_APPEND`).

Перед загрузкой вызывается guard шага 2 (`connector/raw_loader/guard.py`) —
эта функция сама guard не вызывает (порядок — забота вызывающего, `main.py`
шага 5), но принимает уже проверенную схему тем же значением, что guard
сверял, чтобы не рассинхронизировать эталон и загрузку.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Callable, Iterable


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
    """Скачивает объект `gs_path`, парсит построчный JSON. Пустые строки пропускаются.
    Тот же приём, что `functions/cf_daily/bq_loader.read_ndjson_from_gcs`."""
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


def add_loader_columns(
    rows: list[dict], *, loaded_at: datetime.datetime, source_blob: str
) -> list[dict]:
    """Каждой строке — `loaded_at` (ISO-8601) и `source_blob` (путь исходного
    блоба), без них прогон неотличим от предыдущего (ADR-083 п.4)."""
    loaded_at_iso = loaded_at.isoformat()
    out: list[dict] = []
    for row in rows:
        enriched = dict(row)
        enriched["loaded_at"] = loaded_at_iso
        enriched["source_blob"] = source_blob
        out.append(enriched)
    return out


def _default_bq_client_factory(project_id: str | None) -> Any:
    from google.cloud import bigquery  # type: ignore

    return bigquery.Client(project=project_id)


def load_rows_to_bq(
    rows: list[dict],
    *,
    table: str,
    expected_schema: Iterable[tuple[str, str, str]],
    dataset: str = "lombard_ops",
    project_id: str | None = None,
    client_factory: Callable[[str | None], Any] = _default_bq_client_factory,
) -> int:
    """Загружает список строк в `dataset.table` явным списком колонок
    (`bigquery.SchemaField`, не autodetect — `05 §II`). `expected_schema` —
    список `(имя, тип, mode)`, тот же, что строит шаг 1
    (`generate_raw_ddl.table_schema_fields`) и сверяет guard шага 2.
    Возвращает счёт загруженных строк."""
    from google.cloud import bigquery  # type: ignore

    schema = [
        bigquery.SchemaField(name, field_type, mode=mode)
        for name, field_type, mode in expected_schema
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
    return len(rows)


def load_table_blob(
    gs_path: str,
    *,
    table: str,
    expected_schema: Iterable[tuple[str, str, str]],
    project_id: str,
    dataset: str = "lombard_ops",
    now: datetime.datetime | None = None,
    gcs_client_factory: Callable[[str | None], Any] = _default_gcs_client_factory,
    bq_client_factory: Callable[[str | None], Any] = _default_bq_client_factory,
) -> tuple[int, datetime.datetime]:
    """Оркестрация шага 3: читает NDJSON из `gs_path`, добавляет
    `loaded_at`/`source_blob`, загружает в `dataset.table` явным списком
    колонок. Guard (шаг 2) НЕ вызывается здесь — вызывающий код (`main.py`)
    вызывает его перед этой функцией и не загружает при расхождении.
    Возвращает `(счёт строк, loaded_at)`."""
    loaded_at = now or datetime.datetime.now(datetime.timezone.utc)
    raw_rows = read_ndjson_from_gcs(
        gs_path, project_id=project_id, client_factory=gcs_client_factory
    )
    enriched_rows = add_loader_columns(raw_rows, loaded_at=loaded_at, source_blob=gs_path)
    count = load_rows_to_bq(
        enriched_rows,
        table=table,
        expected_schema=expected_schema,
        dataset=dataset,
        project_id=project_id,
        client_factory=bq_client_factory,
    )
    return count, loaded_at
