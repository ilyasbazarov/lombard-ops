"""
connector/raw_loader/test_main.py — T-1-1, шаг 5

Тест точки входа на моках всех трёх внешних клиентов (GCS, BQ, Secret
Manager) плюс Telegram (`http_post`), без сети. Использует РЕАЛЬНЫЙ
`mapping.json` (копия в этом каталоге, `T-0-10`, 9 таблиц/124 колонки) как
источник ожидаемых схем — тот же вход, что и прод.

Два сценария:
  1. Все девять таблиц совпадают с живой схемой -> прогон завершается без
     исключения, счёт строк по каждой таблице возвращён.
  2. Первая по порядку отпечатка таблица (`CONTRACTS`) даёт расхождение
     живой схемы -> **решение исполнителя, подтверждено явно (докстринг
     `main.py`)**: прогон останавливается ЦЕЛИКОМ на первом отказе, алерт
     отправлен (тестовый мок Telegram, не боевой чат), guard/loader
     ОСТАЛЬНЫХ ВОСЬМИ таблиц в тесте не вызываются вовсе — подтверждается
     счётчиком вызовов `bq_client.get_table_calls`/`gcs_client.blob_calls`.

Запуск: `cd connector/raw_loader && python3 test_main.py` — корень импорта
совпадает с контейнером Cloud Run Job (`--source=connector/raw_loader`,
ADR-078 пп.4-5).
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from generate_raw_ddl import load_schema_fingerprint, raw_table_name, table_schema_fields
from main import MAPPING_PATH, RawLoaderStepError, run_pipeline

FINGERPRINT = load_schema_fingerprint(MAPPING_PATH)
TABLE_ORDER = list(FINGERPRINT.keys())  # порядок отпечатка, как в mapping.json
PROJECT_ID = "my-project"
BUCKET = "my-project-cfsource"
RUN_DATE = "2026-08-19"


def _fixture_row(table: str) -> dict:
    """Одна минимальная NDJSON-строка на таблицу — значения по первой колонке
    отпечатка, остальные не несёт (загрузчик не требует полноты для теста
    формы, `add_loader_columns` работает построчно независимо от набора
    полей)."""
    first_col = FINGERPRINT[table][0][0]
    return {first_col: 1}


class FakeSchemaField:
    def __init__(self, name: str, field_type: str):
        self.name = name
        self.field_type = field_type


class FakeBqTable:
    def __init__(self, schema: list[FakeSchemaField]):
        self.schema = schema


class FakeBqClient:
    """Живая схема каждой `raw_<table>` совпадает с ожидаемой, кроме таблиц,
    перечисленных в `mismatched_tables` (там один тип подменён)."""

    def __init__(self, mismatched_tables: set[str] = frozenset()):
        self.get_table_calls: list[str] = []
        self.load_calls: list[tuple[str, list[dict], Any]] = []
        self._mismatched = mismatched_tables

    def get_table(self, table_ref: str) -> FakeBqTable:
        self.get_table_calls.append(table_ref)
        table = table_ref.split(".")[-1]
        firebird_table = next(t for t in TABLE_ORDER if raw_table_name(t) == table)
        expected = table_schema_fields(firebird_table, FINGERPRINT[firebird_table])
        if firebird_table in self._mismatched:
            name0, _type0, mode0 = expected[0]
            expected = [(name0, "BOOL", mode0)] + list(expected[1:])  # тип подменён
        fields = [FakeSchemaField(name, field_type) for name, field_type, _mode in expected]
        return FakeBqTable(fields)

    def load_table_from_json(self, rows, table_ref, job_config=None):
        self.load_calls.append((table_ref, rows, job_config))
        return _FakeLoadJob()


class _FakeLoadJob:
    def result(self) -> None:
        return None


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
    def __init__(self, blobs: dict[str, FakeBlob]):
        self.blob_calls: list[str] = []
        self._bucket = FakeBucket(blobs)
        self._prefixes = [f"agent/{RUN_DATE}/"]

    def bucket(self, name: str) -> FakeBucket:
        return self._bucket

    def list_blobs(self, bucket_name: str, prefix: str, delimiter: str) -> "_FakeIterator":
        return _FakeIterator(self._prefixes)


class _FakeIterator:
    def __init__(self, prefixes: list[str]):
        self.prefixes = prefixes

    def __iter__(self):
        return iter([])


def _make_gcs_client() -> FakeGcsClient:
    blobs = {
        f"agent/{RUN_DATE}/{table}.ndjson": FakeBlob(json.dumps(_fixture_row(table)))
        for table in TABLE_ORDER
    }
    return FakeGcsClient(blobs)


class FakeSecretClient:
    def __init__(self):
        self.calls: list[str] = []

    def access_secret_version(self, name: str):
        self.calls.append(name)

        class _Resp:
            def __init__(self, value: str):
                self.payload = type("P", (), {"data": value.encode("utf-8")})()

        if "telegram-bot-token" in name:
            return _Resp("test-token-value")
        if "chat_id" in name:
            return _Resp(json.dumps({"owner": "12345"}))
        raise AssertionError(f"неожиданный секрет запрошен: {name}")


_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1: все девять таблиц совпадают со схемой — прогон завершается без исключения, 9 загрузок")
def _t1_clean_run_all_nine():
    bq_client = FakeBqClient()
    gcs_client = _make_gcs_client()
    secret_client = FakeSecretClient()
    results = run_pipeline(
        project_id=PROJECT_ID,
        bucket_name=BUCKET,
        mapping_path=MAPPING_PATH,
        storage_client_factory=lambda pid: gcs_client,
        gcs_client_factory=lambda pid: gcs_client,
        bq_client_factory=lambda pid: bq_client,
        secret_client_factory=lambda: secret_client,
    )
    assert len(results) == 9, f"ожидалось 9 таблиц загружено, получено {len(results)}"
    assert len(bq_client.load_calls) == 9
    assert secret_client.calls == [], "секреты не читаются вовсе, если алерта не было"


@check(
    "2: расхождение на ПЕРВОЙ таблице (CONTRACTS) — прогон останавливается ЦЕЛИКОМ, "
    "алерт отправлен, остальные восемь НЕ тронуты (0 загрузок)"
)
def _t2_first_table_mismatch_stops_whole_run():
    mismatched_table = TABLE_ORDER[0]  # CONTRACTS — первая по порядку отпечатка
    bq_client = FakeBqClient(mismatched_tables={mismatched_table})
    gcs_client = _make_gcs_client()
    secret_client = FakeSecretClient()
    telegram_calls: list[tuple[str, bytes]] = []

    def fake_http_post(url: str, data: bytes) -> dict:
        telegram_calls.append((url, data))
        return {"ok": True, "result": {"message_id": 999}}

    try:
        run_pipeline(
            project_id=PROJECT_ID,
            bucket_name=BUCKET,
            mapping_path=MAPPING_PATH,
            storage_client_factory=lambda pid: gcs_client,
            gcs_client_factory=lambda pid: gcs_client,
            bq_client_factory=lambda pid: bq_client,
            secret_client_factory=lambda: secret_client,
            http_post=fake_http_post,
        )
        raise AssertionError("расхождение схемы обязано остановить прогон, а он прошёл")
    except RawLoaderStepError as exc:
        assert exc.table == mismatched_table

    # guard проверил ровно ОДНУ таблицу (упавшую) — до неё в порядке отпечатка ничего нет
    assert bq_client.get_table_calls == [
        f"{PROJECT_ID}.lombard_ops.{raw_table_name(mismatched_table)}"
    ], f"guard обязан остановиться на первой же таблице, вызовы: {bq_client.get_table_calls}"
    # загрузка НЕ была вызвана ни для одной из девяти — guard стоит ПЕРЕД loader
    assert bq_client.load_calls == [], (
        f"ни одна из девяти таблиц (включая остальные восемь) не должна грузиться "
        f"при стопе на первой — загружено: {[c[0] for c in bq_client.load_calls]}"
    )
    # алерт отправлен (тестовый мок, не боевой чат) с именем упавшей таблицы
    assert len(telegram_calls) == 1, "алерт обязан быть отправлен ровно один раз"
    url, payload = telegram_calls[0]
    assert "test-token-value" in url
    body = json.loads(payload.decode("utf-8"))
    assert raw_table_name(mismatched_table) in body["text"]
    assert body["chat_id"] == "12345"
    # секреты прочитаны ровно один раз каждый (алерт, не повторная отправка/ретрай)
    assert len(secret_client.calls) == 2


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
