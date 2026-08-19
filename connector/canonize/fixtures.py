"""
connector/canonize/fixtures.py — T-1-2a

Билдеры строк слоя сырья для офлайн-теста `sql/canonization.sql`. Данные
синтетические, построены этой сессией (не читались нигде ранее) — заводятся
только тестом, объект замера не выдуман (`ADR-063` R2).
"""

from __future__ import annotations

import datetime

import duckdb

FIXTURE_BLOB = "test-fixtures/T-1-2a/fixture.ndjson"


def insert_contract_state(
    con: duckdb.DuckDBPyConnection,
    state_id: int,
    code: str,
    sort_order: int = 0,
    loaded_at: str = "2026-08-01 00:00:00",
    source_blob: str = FIXTURE_BLOB,
) -> None:
    con.execute(
        "INSERT INTO lombard_ops.raw_contract_states VALUES (?, ?, ?, ?, ?)",
        [state_id, code, sort_order, loaded_at, source_blob],
    )


def insert_contract(
    con: duckdb.DuckDBPyConnection,
    contract_id: int,
    contract_state: int,
    contract_date: str,
    plan_close_date: str,
    id_prev_contract: int | None = None,
    loaded_at: str = "2026-08-01 00:00:00",
    source_blob: str = FIXTURE_BLOB,
) -> None:
    con.execute(
        "INSERT INTO lombard_ops.raw_contracts VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            contract_id,
            contract_state,
            contract_date,
            id_prev_contract,
            plan_close_date,
            loaded_at,
            source_blob,
        ],
    )


def insert_operation(
    con: duckdb.DuckDBPyConnection,
    op_id: int,
    deposit_id: int,
    op_vid: int,
    op_date: str,
    loaded_at: str = "2026-08-01 00:00:00",
    source_blob: str = FIXTURE_BLOB,
) -> None:
    con.execute(
        "INSERT INTO lombard_ops.raw_operations VALUES (?, ?, ?, ?, ?, ?)",
        [op_id, deposit_id, op_vid, op_date, loaded_at, source_blob],
    )


# CONTRACT_STATES.code, справочник дословно из T-0-4a
# (reference/T-0-4a_renewal_detector_measurement_2026-08-18.md, шаг 12).
STATE_OPEN = 0
STATE_CLOSED = 1
STATE_SALED = 2
STATE_ONSALE = 3
STATE_SENT2CO = 4
STATE_SHOP = 5

STATE_CODES = {
    STATE_OPEN: "OPEN",
    STATE_CLOSED: "CLOSED",
    STATE_SALED: "SALED",
    STATE_ONSALE: "ONSALE",
    STATE_SENT2CO: "SENT2CO",
    STATE_SHOP: "SHOP",
}


def seed_contract_states(con: duckdb.DuckDBPyConnection) -> None:
    for state_id, code in STATE_CODES.items():
        insert_contract_state(con, state_id, code)


ANCHOR_DUE_DATE = datetime.date(2026, 1, 1)
