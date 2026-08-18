"""
functions/cf_daily/test_main.py — T-1-0, шаг 4

Тест точки входа `cf_daily` на моках всех четырёх внешних клиентов (GCS, BQ,
Secret Manager, Telegram) — без сети. Запуск:
`python3 -m functions.cf_daily.test_main` из корня репозитория.
"""

from __future__ import annotations

import datetime
import json
import sys
import traceback
from typing import Any

from functions.cf_daily.main import (
    PipelineError,
    find_latest_contracts_blob,
    run_pipeline,
    select_one_contract,
)

FIXTURE_NDJSON = "\n".join(
    [
        '{"CONTRACT_ID": 1003, "CONTRACT_DATE": "2026-07-10", "PLAN_CLOSE_DATE": "2026-08-09", "DEPOSIT_SUM": "200000"}',
        '{"CONTRACT_ID": 1001, "CONTRACT_DATE": "2026-07-01", "PLAN_CLOSE_DATE": "2026-07-30", "DEPOSIT_SUM": "150000"}',
        '{"CONTRACT_ID": 1002, "CONTRACT_DATE": "2026-07-05", "PLAN_CLOSE_DATE": "", "DEPOSIT_SUM": "75050"}',
    ]
)

# ---------------------------------------------------------------------------
# Фиктивные клиенты
# ---------------------------------------------------------------------------


class FakeBlobIterator:
    """Имитирует поведение `google.cloud.storage.Client.list_blobs(..., delimiter="/")`:
    после итерирования несёт атрибут `.prefixes`."""

    def __init__(self, prefixes: list[str]):
        self.prefixes = set(prefixes)

    def __iter__(self):
        return iter(())


class FakeStorageClientForListing:
    def __init__(self, prefixes: list[str]):
        self._prefixes = prefixes

    def list_blobs(self, bucket_or_name, prefix=None, delimiter=None):
        return FakeBlobIterator(self._prefixes)


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


class FakeStorageClientForRead:
    def __init__(self, buckets: dict[str, FakeBucket]):
        self._buckets = buckets

    def bucket(self, name: str) -> FakeBucket:
        return self._buckets[name]


class FakeLoadJob:
    def result(self) -> None:
        return None


class FakeBqClient:
    def __init__(self):
        self.load_calls: list[Any] = []

    def load_table_from_json(self, rows, table_ref, job_config=None):
        self.load_calls.append((rows, table_ref))
        return FakeLoadJob()


class FakeSecretPayload:
    def __init__(self, value: str):
        self.data = value.encode("utf-8")


class FakeSecretResponse:
    def __init__(self, value: str):
        self.payload = FakeSecretPayload(value)


class FakeSecretClient:
    def __init__(self, values: dict[str, str]):
        self._values = values

    def access_secret_version(self, name: str):
        # name = projects/<p>/secrets/<secret_id>/versions/<version>
        secret_id = name.split("/secrets/")[1].split("/versions/")[0]
        return FakeSecretResponse(self._values[secret_id])


def fake_http_post_ok(url: str, data: bytes) -> dict:
    return {"ok": True, "result": {"message_id": 42, "date": 1, "chat": {"id": -1, "type": "group"}}}


# ---------------------------------------------------------------------------
# Реестр проверок
# ---------------------------------------------------------------------------

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1: find_latest_contracts_blob выбирает МАКСИМАЛЬНУЮ дату из нескольких каталогов")
def _t1_find_latest():
    client = FakeStorageClientForListing(["agent/2026-08-15/", "agent/2026-08-17/", "agent/2026-08-16/"])
    gs_path = find_latest_contracts_blob(
        "proj-cfsource", project_id="proj", client_factory=lambda pid: client
    )
    assert gs_path == "gs://proj-cfsource/agent/2026-08-17/CONTRACTS.ndjson", gs_path


@check("2: find_latest_contracts_blob — пустой бакет поднимает исключение, не тихий None")
def _t2_find_latest_empty():
    client = FakeStorageClientForListing([])
    try:
        find_latest_contracts_blob("proj-cfsource", project_id="proj", client_factory=lambda pid: client)
        raise AssertionError("пустой бакет обязан поднять исключение, а прошёл")
    except RuntimeError:
        pass


@check("3: select_one_contract — первый по возрастанию contract_id с непустым due_date")
def _t3_select_one():
    rows = [
        {"contract_id": "1003", "due_date": "2026-08-09"},
        {"contract_id": "1001", "due_date": "2026-07-30"},
        {"contract_id": "1002", "due_date": ""},
    ]
    picked = select_one_contract(rows)
    assert picked["contract_id"] == "1001", picked


@check("4: run_pipeline — полный конвейер (а)-(е) на моках всех четырёх клиентов, зелёный путь")
def _t4_full_pipeline_green():
    storage_listing_client = FakeStorageClientForListing(["agent/2026-08-17/"])
    storage_read_client = FakeStorageClientForRead(
        {"my-project-cfsource": FakeBucket({"agent/2026-08-17/CONTRACTS.ndjson": FakeBlob(FIXTURE_NDJSON)})}
    )
    bq_client = FakeBqClient()
    secret_client = FakeSecretClient(
        {"telegram-bot-token": "FAKE_TOKEN", "chat_id": json.dumps({"owner": -1000000001})}
    )

    result = run_pipeline(
        project_id="my-project",
        bucket_name="my-project-cfsource",
        today=datetime.date(2026, 8, 18),
        storage_client_factory=lambda pid: storage_listing_client,
        gcs_client_factory=lambda pid: storage_read_client,
        bq_client_factory=lambda pid: bq_client,
        secret_client_factory=lambda: secret_client,
        http_post=fake_http_post_ok,
    )

    assert result["row_count"] == 3, result
    assert result["contract_id"] == "1001", result  # наименьший с непустым due_date
    # смещение 2026-08-18 - 2026-07-30 = +19 дней -> 🟠 Пре-маркетинг (16..31)
    assert result["status"] == "🟠 Пре-маркетинг", result
    assert result["message_id"] == "42", result
    assert len(bq_client.load_calls) == 1


@check("5: run_pipeline — отказ Telegram (шаг д) поднимает PipelineError с именем шага, не тихий успех")
def _t5_pipeline_step_d_fails():
    storage_listing_client = FakeStorageClientForListing(["agent/2026-08-17/"])
    storage_read_client = FakeStorageClientForRead(
        {"my-project-cfsource": FakeBucket({"agent/2026-08-17/CONTRACTS.ndjson": FakeBlob(FIXTURE_NDJSON)})}
    )
    bq_client = FakeBqClient()
    secret_client = FakeSecretClient(
        {"telegram-bot-token": "FAKE_TOKEN", "chat_id": json.dumps({"owner": -1000000001})}
    )

    def failing_http_post(url: str, data: bytes) -> dict:
        return {"ok": False, "error_code": 400, "description": "forbidden"}

    try:
        run_pipeline(
            project_id="my-project",
            bucket_name="my-project-cfsource",
            today=datetime.date(2026, 8, 18),
            storage_client_factory=lambda pid: storage_listing_client,
            gcs_client_factory=lambda pid: storage_read_client,
            bq_client_factory=lambda pid: bq_client,
            secret_client_factory=lambda: secret_client,
            http_post=failing_http_post,
        )
        raise AssertionError("отказ Telegram обязан поднять PipelineError, а прошёл тихо")
    except PipelineError as exc:
        assert exc.step.startswith("д"), f"ожидался отказ на шаге (д), получено {exc.step!r}"


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
