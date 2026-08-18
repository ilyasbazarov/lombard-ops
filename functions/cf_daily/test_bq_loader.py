"""
functions/cf_daily/test_bq_loader.py — T-1-0, шаг 1

Тест загрузчика BQ на фикстуре из 2-3 строк, без сети — GCS и BQ-клиент мокнуты
фиктивными объектами. Запуск: `python3 -m functions.cf_daily.test_bq_loader` из
корня репозитория — печатает `провалено N`.
"""

from __future__ import annotations

import datetime
import decimal
import sys
import traceback
from typing import Any

from functions.cf_daily.bq_loader import (
    GcsPathError,
    LOANS_RAW_SCHEMA_FIELDS,
    load_contracts_blob,
    map_contract_row,
    parse_gs_path,
)

# ---------------------------------------------------------------------------
# Фиктивные GCS/BQ клиенты — к сети не обращаются.
# ---------------------------------------------------------------------------

FIXTURE_NDJSON = "\n".join(
    [
        '{"CONTRACT_ID": 1001, "CONTRACT_DATE": "2026-07-01", "PLAN_CLOSE_DATE": "2026-07-30", "DEPOSIT_SUM": "150000"}',
        '{"CONTRACT_ID": 1002, "CONTRACT_DATE": "2026-07-05", "PLAN_CLOSE_DATE": "2026-08-04", "DEPOSIT_SUM": "75050"}',
        '{"CONTRACT_ID": 1003, "CONTRACT_DATE": "2026-07-10", "PLAN_CLOSE_DATE": "2026-08-09", "DEPOSIT_SUM": "200000"}',
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


# ---------------------------------------------------------------------------
# Реестр проверок
# ---------------------------------------------------------------------------

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1: parse_gs_path разбирает gs://bucket/blob корректно")
def _t1_parse_ok():
    bucket, blob = parse_gs_path("gs://project-cfsource/agent/2026-08-17/CONTRACTS.ndjson")
    assert bucket == "project-cfsource"
    assert blob == "agent/2026-08-17/CONTRACTS.ndjson"


@check("1-БИС: parse_gs_path отбивает не-gs:// путь (контраст с проверкой 1)")
def _t1bis_parse_rejects():
    try:
        parse_gs_path("https://example.com/blob")
        raise AssertionError("не-gs:// путь обязан быть отбит, а прошёл")
    except GcsPathError:
        pass


@check("2: map_contract_row — DEPOSIT_SUM делится на 100 строкой, даты копируются")
def _t2_map_row():
    row = {
        "CONTRACT_ID": 1001,
        "CONTRACT_DATE": "2026-07-01",
        "PLAN_CLOSE_DATE": "2026-07-30",
        "DEPOSIT_SUM": "150000",
    }
    loaded_at = datetime.datetime(2026, 8, 18, 3, 0, tzinfo=datetime.timezone.utc)
    mapped = map_contract_row(row, loaded_at=loaded_at)
    assert mapped["contract_id"] == "1001"
    assert mapped["issue_date"] == "2026-07-01"
    assert mapped["due_date"] == "2026-07-30"
    assert decimal.Decimal(mapped["loan_amount"]) == decimal.Decimal("1500.00")
    assert mapped["loaded_at"] == loaded_at.isoformat()
    # частичный маппинг — остальные колонки NULL сознательно
    for null_col in (
        "vehicle_id",
        "client_name",
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "status_raw",
        "renewed",
        "renewed_date",
    ):
        assert mapped[null_col] is None, f"{null_col} обязана быть NULL, а не {mapped[null_col]}"


@check("3: load_contracts_blob — фикстура из 3 строк, счёт и схема БЕЗ autodetect")
def _t3_load_fixture():
    gcs_client = FakeGcsClient(
        {
            "project-cfsource": FakeBucket(
                {"agent/2026-08-17/CONTRACTS.ndjson": FakeBlob(FIXTURE_NDJSON)}
            )
        }
    )
    bq_client = FakeBqClient()
    count, loaded_at, mapped_rows = load_contracts_blob(
        "gs://project-cfsource/agent/2026-08-17/CONTRACTS.ndjson",
        project_id="my-project",
        now=datetime.datetime(2026, 8, 18, 3, 0, tzinfo=datetime.timezone.utc),
        gcs_client_factory=lambda project_id: gcs_client,
        bq_client_factory=lambda project_id: bq_client,
    )
    assert count == 3, f"ожидалось 3 строки, получено {count}"
    assert len(mapped_rows) == 3
    assert len(bq_client.load_calls) == 1
    _, table_ref, job_config = bq_client.load_calls[0]
    assert table_ref == "my-project.lombard_ops.loans_raw"
    schema_names = [field.name for field in job_config.schema]
    assert schema_names == [name for name, _, _ in LOANS_RAW_SCHEMA_FIELDS], (
        "schema обязана быть явной и совпадать с DDL, autodetect запрещён (05 §II)"
    )
    assert job_config.autodetect in (None, False), "autodetect обязан быть выключен"


def main() -> int:
    failed = 0
    for name, fn in _checks:
        try:
            fn()
        except Exception:  # noqa: BLE001 — тест обязан печатать провал, не падать молча
            failed += 1
            print(f"[ПРОВАЛЕНО] {name}")
            traceback.print_exc()
        else:
            print(f"[пройдено]  {name}")
    print(f"\nвсего проверок: {len(_checks)}; провалено {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
