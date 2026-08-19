"""
connector/test_generate_raw_ddl.py — T-1-1, шаг 1

Тесты генератора DDL слоя сырья, на фикстурах (копии/подмножестве реального
`schema_fingerprint`) и на РЕАЛЬНОМ `connector/mapping.json` — без сети, без
BigQuery. Запуск: `cd connector && python3 test_generate_raw_ddl.py` — корень
импорта совпадает с тем, что деплой Cloud Run Job (`--source=connector`) даёт
контейнеру (ADR-078 пп.4-5).
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

from generate_raw_ddl import (
    MAPPING_PATH,
    UnknownTypeCode,
    bq_type_for_column,
    generate_raw_ddl,
    generate_table_ddl,
    load_schema_fingerprint,
    raw_table_name,
)

# ---------------------------------------------------------------------------
# Фикстура — подмножество реального schema_fingerprint (T-0-10), по одной-две
# колонки на закрытый код типа, чтобы приёмка видела все семь веток разом.
# ---------------------------------------------------------------------------

FIXTURE_FINGERPRINT: dict[str, list[list[Any]]] = {
    "CONTRACT_STATES": [
        ["STATE_ID", 7, 2, 0],  # SMALLINT -> INT64
        ["CODE", 37, 320, 0],  # VARCHAR -> STRING
    ],
    "CONTRACTS": [
        ["CONTRACT_ID", 8, 4, 0],  # INTEGER -> INT64
        ["CONTRACT_DATE", 12, 4, 0],  # DATE -> DATE
        ["DEPOSIT_SUM", 16, 8, 0],  # BIGINT (scale=0) -> INT64
    ],
    "CONTRACTS_TERMS": [
        ["DEPOSIT_PERC", 16, 8, -5],  # NUMERIC (scale<0) -> NUMERIC
    ],
    "OPERATIONS": [
        ["OP_DATE", 35, 8, 0],  # TIMESTAMP -> TIMESTAMP
    ],
}

FIXTURE_MAPPING = {"schema_fingerprint": FIXTURE_FINGERPRINT}

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1: raw_table_name — нижний регистр, префикс raw_")
def _t1_raw_table_name():
    assert raw_table_name("CONTRACTS_TERMS") == "raw_contracts_terms"
    assert raw_table_name("OPERATIONS") == "raw_operations"


@check("2: bq_type_for_column — все семь закрытых кодов дают верный тип")
def _t2_type_map():
    assert bq_type_for_column("T", "C", 7, 0) == "INT64"
    assert bq_type_for_column("T", "C", 8, 0) == "INT64"
    assert bq_type_for_column("T", "C", 12, 0) == "DATE"
    assert bq_type_for_column("T", "C", 16, 0) == "INT64"
    assert bq_type_for_column("T", "C", 16, -5) == "NUMERIC"
    assert bq_type_for_column("T", "C", 27, 0) == "FLOAT64"
    assert bq_type_for_column("T", "C", 35, 0) == "TIMESTAMP"
    assert bq_type_for_column("T", "C", 37, 0) == "STRING"


@check("3: код типа вне закрытого списка (999) даёт UnknownTypeCode с именем таблицы/колонки/кода")
def _t3_unknown_type_code_rejected():
    try:
        bq_type_for_column("CONTRACTS", "MUTATED_COL", 999, 0)
        raise AssertionError("код 999 обязан быть отбит, а прошёл")
    except UnknownTypeCode as exc:
        assert exc.table == "CONTRACTS"
        assert exc.column == "MUTATED_COL"
        assert exc.code == 999
        assert "999" in str(exc)


@check("3-БИС: обратный замер — нетронутая фикстура генератор проходит без исключения (контраст к 3)")
def _t3bis_reverse_measurement_clean_fixture_passes():
    ddl = generate_raw_ddl(FIXTURE_MAPPING)  # исключения не подняло — обратный замер к проверке 3
    assert "raw_contracts" in ddl


@check("4: generate_table_ddl — служебные колонки loaded_at/source_blob присутствуют")
def _t4_service_columns():
    ddl = generate_table_ddl("CONTRACTS", FIXTURE_FINGERPRINT["CONTRACTS"])
    assert "loaded_at TIMESTAMP NOT NULL" in ddl
    assert "source_blob STRING NOT NULL" in ddl
    assert "CREATE TABLE IF NOT EXISTS `lombard_ops.raw_contracts`" in ddl


@check("5: generate_raw_ddl на фикстуре — одна CREATE TABLE на таблицу отпечатка")
def _t5_full_fixture_ddl():
    ddl = generate_raw_ddl(FIXTURE_MAPPING)
    for table in FIXTURE_FINGERPRINT:
        assert f"`lombard_ops.{raw_table_name(table)}`" in ddl, f"{table} отсутствует в DDL"
    assert ddl.count("CREATE TABLE IF NOT EXISTS") == len(FIXTURE_FINGERPRINT)


@check("6: подмена одного кода фикстуры (8 -> 999) стопит генератор целиком — отказ лога")
def _t6_mutated_fixture_stops_generation():
    mutated = {
        "schema_fingerprint": {
            "CONTRACTS": [
                ["CONTRACT_ID", 999, 4, 0],  # мутирован: было 8 (INTEGER)
                ["CONTRACT_DATE", 12, 4, 0],
            ]
        }
    }
    try:
        generate_raw_ddl(mutated)
        raise AssertionError("мутированный код типа обязан стопить генератор, а прошёл")
    except UnknownTypeCode as exc:
        assert exc.table == "CONTRACTS"
        assert exc.column == "CONTRACT_ID"
        assert exc.code == 999


@check("7: load_schema_fingerprint — путь к отсутствующему разделу даёт ValueError (CONTEXT GAP)")
def _t7_missing_fingerprint_section():
    try:
        load_schema_fingerprint({"no_fingerprint_here": True})
        raise AssertionError("отсутствие schema_fingerprint обязано быть отбито")
    except ValueError as exc:
        assert "CONTEXT GAP" in str(exc)


@check("8: реальный connector/mapping.json — 9 таблиц, 124 колонки, все коды из закрытого списка")
def _t8_real_mapping_fingerprint():
    assert MAPPING_PATH.exists(), f"CONTEXT GAP: {MAPPING_PATH} не найден"
    fingerprint = load_schema_fingerprint(MAPPING_PATH)
    assert len(fingerprint) == 9, f"ожидалось 9 таблиц, получено {len(fingerprint)}"
    total_columns = sum(len(cols) for cols in fingerprint.values())
    assert total_columns == 124, f"ожидалось 124 колонки, получено {total_columns}"
    # реальный отпечаток обязан пройти генератор целиком без UnknownTypeCode
    ddl = generate_raw_ddl(MAPPING_PATH)
    assert ddl.count("CREATE TABLE IF NOT EXISTS") == 9


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
