"""
connector/raw_loader/test_loader.py — T-1-1, шаг 3

Тест загрузчика на фикстуре из 2-3 строк NDJSON, моки GCS и BQ-клиентов, без
сети. Запуск: `cd connector/raw_loader && python3 test_loader.py` — корень
импорта совпадает с контейнером (ADR-078 пп.4-5).
"""

from __future__ import annotations

import datetime
import sys
import traceback
from typing import Any

from loader import (
    GcsPathError,
    add_loader_columns,
    load_table_blob,
    parse_gs_path,
)

EXPECTED_SCHEMA = [
    ("state_id", "INT64", "NULLABLE"),
    ("code", "STRING", "NULLABLE"),
    ("loaded_at", "TIMESTAMP", "REQUIRED"),
    ("source_blob", "STRING", "REQUIRED"),
]

FIXTURE_NDJSON = "\n".join(
    [
        '{"STATE_ID": 1, "CODE": "OPEN"}',
        '{"STATE_ID": 2, "CODE": "CLOSED"}',
        '{"STATE_ID": 3, "CODE": "OVERDUE"}',
    ]
)


class FakeBlob:
    def __init__(self, text: str):
        self._text = text

    def download_as_text(self) -> str:
        return self._text


class FakeBucket:
    def __init__(self, blobs: dict[str, FakeBlob]):
        self._blobs = blobs

    def blob(self, name: str) -> FakeBlob:
        return self._blobs[name]


class FakeGcsClient:
    def __init__(self, buckets: dict[str, FakeBucket]):
        self._buckets = buckets

    def bucket(self, name: str) -> FakeBucket:
        return self._buckets[name]


class FakeLoadJob:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def result(self) -> None:
        return None


class FakeBqClient:
    def __init__(self):
        self.load_calls: list[tuple[list[dict], str, Any]] = []

    def load_table_from_json(self, rows, table_ref, job_config=None):
        self.load_calls.append((rows, table_ref, job_config))
        return FakeLoadJob(rows)


_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1: parse_gs_path разбирает gs://bucket/blob корректно")
def _t1_parse_ok():
    bucket, blob = parse_gs_path("gs://project-cfsource/agent/2026-08-19/CONTRACT_STATES.ndjson")
    assert bucket == "project-cfsource"
    assert blob == "agent/2026-08-19/CONTRACT_STATES.ndjson"


@check("1-БИС: parse_gs_path отбивает не-gs:// путь (контраст с 1)")
def _t1bis_parse_rejects():
    try:
        parse_gs_path("https://example.com/blob")
        raise AssertionError("не-gs:// путь обязан быть отбит, а прошёл")
    except GcsPathError:
        pass


@check("2: add_loader_columns — loaded_at и source_blob добавлены каждой строке")
def _t2_add_columns():
    loaded_at = datetime.datetime(2026, 8, 19, 4, 0, tzinfo=datetime.timezone.utc)
    rows = [{"STATE_ID": 1}, {"STATE_ID": 2}]
    enriched = add_loader_columns(rows, loaded_at=loaded_at, source_blob="gs://x/y.ndjson")
    assert all(r["loaded_at"] == loaded_at.isoformat() for r in enriched)
    assert all(r["source_blob"] == "gs://x/y.ndjson" for r in enriched)
    assert enriched[0]["STATE_ID"] == 1  # исходные поля не потеряны


@check("3: load_table_blob — фикстура из 3 строк, счёт совпадает, схема БЕЗ autodetect")
def _t3_load_fixture():
    gcs_client = FakeGcsClient(
        {
            "project-cfsource": FakeBucket(
                {
                    "agent/2026-08-19/CONTRACT_STATES.ndjson": FakeBlob(FIXTURE_NDJSON)
                }
            )
        }
    )
    bq_client = FakeBqClient()
    count, loaded_at = load_table_blob(
        "gs://project-cfsource/agent/2026-08-19/CONTRACT_STATES.ndjson",
        table="raw_contract_states",
        expected_schema=EXPECTED_SCHEMA,
        project_id="my-project",
        now=datetime.datetime(2026, 8, 19, 4, 0, tzinfo=datetime.timezone.utc),
        gcs_client_factory=lambda project_id: gcs_client,
        bq_client_factory=lambda project_id: bq_client,
    )
    assert count == 3, f"ожидалось 3 строки в BigQuery, получено {count} (сходимость со счётом NDJSON)"
    assert len(bq_client.load_calls) == 1
    rows, table_ref, job_config = bq_client.load_calls[0]
    assert table_ref == "my-project.lombard_ops.raw_contract_states"
    assert len(rows) == 3, f"NDJSON нёс 3 строки построчным wc -l, загружено {len(rows)}"
    schema_names = [field.name for field in job_config.schema]
    assert schema_names == [name for name, _, _ in EXPECTED_SCHEMA], (
        "schema обязана быть явной и совпадать с эталоном шага 1, autodetect запрещён (05 §II)"
    )
    assert job_config.autodetect in (None, False), "autodetect обязан быть выключен"
    assert all("loaded_at" in r and "source_blob" in r for r in rows)


def main() -> int:
    failed = 0
    for name, fn in _checks:
        try:
            fn()
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"[ПРОВАЛЕНО] {name}")
            traceback.print_exc()
        else:
            print(f"[пройдено]  {name}")
    print(f"\nвсего проверок: {len(_checks)}; провалено {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
