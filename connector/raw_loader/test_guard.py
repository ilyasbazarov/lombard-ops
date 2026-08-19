"""
connector/raw_loader/test_guard.py — T-1-1, шаг 2

Тест guard'а на моке BQ-клиента, без сети: (а) подмена одного типа в моковой
живой схеме -> стоп, лог отказа предъявлен; (б) нетронутая схема (равна
ожидаемой) -> проход, лог предъявлен (обратный замер, `05 §I`
«Наблюдение»). Запуск: `cd connector/raw_loader && python3 test_guard.py` —
корень импорта совпадает с контейнером Cloud Run Job (`--source=connector/raw_loader`,
ADR-078 пп.4-5).
"""

from __future__ import annotations

import sys
import traceback
from typing import Any

from guard import (
    SchemaLoadGuardMismatch,
    check_schema,
    expected_schema_pairs,
    live_schema_pairs,
)

EXPECTED_SCHEMA = [
    ("contract_id", "INT64", "NULLABLE"),
    ("contract_date", "DATE", "NULLABLE"),
    ("deposit_perc", "NUMERIC", "NULLABLE"),
    ("loaded_at", "TIMESTAMP", "REQUIRED"),
    ("source_blob", "STRING", "REQUIRED"),
]


class FakeSchemaField:
    def __init__(self, name: str, field_type: str):
        self.name = name
        self.field_type = field_type


class FakeTable:
    def __init__(self, schema: list[FakeSchemaField]):
        self.schema = schema


class FakeBqClient:
    def __init__(self, table_ref_to_schema: dict[str, list[FakeSchemaField]]):
        self._tables = table_ref_to_schema

    def get_table(self, table_ref: str) -> FakeTable:
        return FakeTable(self._tables[table_ref])


def _matching_live_schema() -> list[FakeSchemaField]:
    return [FakeSchemaField(name, field_type) for name, field_type, _mode in EXPECTED_SCHEMA]


def _mutated_live_schema() -> list[FakeSchemaField]:
    # deposit_perc NUMERIC -> подменён на FLOAT64 (тип "похож", но не эталон)
    fields = _matching_live_schema()
    for f in fields:
        if f.name == "deposit_perc":
            f.field_type = "FLOAT64"
    return fields


_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1: expected_schema_pairs/live_schema_pairs — mode игнорируется, регистр нормализован")
def _t1_pairs():
    pairs = expected_schema_pairs(EXPECTED_SCHEMA)
    assert ("loaded_at", "TIMESTAMP") in pairs
    live = live_schema_pairs([FakeSchemaField("Loaded_At", "TIMESTAMP")])
    assert ("loaded_at", "TIMESTAMP") in live


@check("2: подмена одного типа в живой схеме -> SchemaLoadGuardMismatch, лог отказа с обеими сторонами")
def _t2_mismatch_stops():
    bq_client = FakeBqClient({"my-project.lombard_ops.raw_contracts": _mutated_live_schema()})
    try:
        check_schema(
            "raw_contracts",
            EXPECTED_SCHEMA,
            project_id="my-project",
            client_factory=lambda project_id: bq_client,
        )
        raise AssertionError("расхождение схемы обязано быть отбито, а прошло")
    except SchemaLoadGuardMismatch as exc:
        assert exc.table == "raw_contracts"
        assert ("deposit_perc", "NUMERIC") in exc.expected
        assert ("deposit_perc", "FLOAT64") in exc.actual
        assert "SchemaLoadGuardMismatch" in str(exc)


@check("3 (обратный замер, контраст к 2): нетронутая живая схема — guard проходит без исключения")
def _t3_clean_schema_passes():
    bq_client = FakeBqClient({"my-project.lombard_ops.raw_contracts": _matching_live_schema()})
    check_schema(
        "raw_contracts",
        EXPECTED_SCHEMA,
        project_id="my-project",
        client_factory=lambda project_id: bq_client,
    )
    # исключения не поднято — это и есть проход


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
