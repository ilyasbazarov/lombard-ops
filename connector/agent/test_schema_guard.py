"""
connector/agent/test_schema_guard.py — T-0-10, `ADR-080` п.3

Юнит-тест `schema_guard.guard_check` БЕЗ живого запроса к БД клиента: подключение и
транзакция подменены тем же приёмом, что `connector/agent/test_access_point.py` —
`FakeConnection`/`FakeTransaction`/`FakeCursor`. Эталон берётся из `connector/mapping.json`
(источник переключён `ADR-080`), измерение — из mock-курсора, а не из реальной базы.

Пара случаев:
  (а) untouched — mock возвращает ровно те строки, что несёт `mapping.json`
      `schema_fingerprint` по каждой used-таблице → `guard_check` проходит молча,
      возвращает измеренные данные, `SchemaGuardMismatch` не бросается.
  (б) искажённый — один тип (`FIELD_TYPE`) одной колонки одной used-таблицы подменён
      в измерении → `guard_check` бросает `SchemaGuardMismatch`; ни одна из девяти
      таблиц не считается прочитанной в смысле guard'а (расхождение стопит ВЕСЬ
      снимок, не одну таблицу — это уже гарантирует сам `guard_check`, тест это
      проверяет по факту исключения и по тому, что chit `guard_check` не возвращает
      результат вовсе).

Запуск: `python3 -m connector.agent.test_schema_guard` из корня репозитория —
печатает `провалено N`; `провалено 0` и есть вердикт (правило наблюдения `05 §I`).
"""

from __future__ import annotations

import sys
import traceback
from typing import Any

from connector.agent import schema_guard
from connector.agent.access_point import ALLOWED_TABLES

MAPPING = schema_guard.load_reference(schema_guard.MAPPING_PATH)
assert MAPPING is not None, "connector/mapping.json обязан нести schema_fingerprint для этого теста"
assert sorted(MAPPING.keys()) == sorted(ALLOWED_TABLES), (
    "эталон mapping.json расходится с ALLOWED_TABLES — тест не может опираться "
    "на посторонний список таблиц"
)

TABLE_NAMES = sorted(ALLOWED_TABLES)


# ---------------------------------------------------------------------------
# Фиктивное соединение — подменяет fdb, к серверу не обращается. Каждой таблице
# соответствует свой набор строк отпечатка (передаётся мапом снаружи), курсор
# отдаёт ИМЕННО те строки, что запрошены в WHERE RDB$RELATION_NAME = ?.
# ---------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, rows_by_table: dict[str, list[tuple]]):
        self._rows_by_table = rows_by_table
        self._last_result: list[tuple] | None = None

    def execute(self, sql: str, params=()) -> None:
        if "MON$TRANSACTIONS" in sql and "MON$READ_ONLY" in sql:
            self._last_result = [(1,)]  # read-only подтверждён положительным фактом
            return
        table = params[0]
        self._last_result = list(self._rows_by_table.get(table, []))

    def fetchone(self):
        return self._last_result[0] if self._last_result else None

    def fetchall(self):
        return list(self._last_result or [])

    def close(self) -> None:
        pass


class FakeTransaction:
    def __init__(self, rows_by_table: dict[str, list[tuple]]):
        self._rows_by_table = rows_by_table

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows_by_table)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class FakeConnection:
    def __init__(self, rows_by_table: dict[str, list[tuple]]):
        self.rows_by_table = rows_by_table
        self.trans_calls = 0

    def open_transaction(self) -> FakeTransaction:
        self.trans_calls += 1
        return FakeTransaction(self.rows_by_table)


def _factory(connection: FakeConnection) -> FakeTransaction:
    return connection.open_transaction()


def _rows_from_mapping(mapping: dict[str, list[list[Any]]]) -> dict[str, list[tuple]]:
    """`mapping.json["schema_fingerprint"][table]` → строки, какие вернул бы
    `access_point`/`fingerprint_table` при точном совпадении с эталоном."""
    return {table: [tuple(row) for row in cols] for table, cols in mapping.items()}


# ---------------------------------------------------------------------------
# Реестр проверок — тот же приём, что test_access_point.py.
# ---------------------------------------------------------------------------

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("(а) untouched: измеренное совпадает с mapping.json — guard_check проходит молча")
def _t_untouched():
    rows_by_table = _rows_from_mapping(MAPPING)
    conn = FakeConnection(rows_by_table)
    result = schema_guard.guard_check(
        conn, TABLE_NAMES, path=schema_guard.MAPPING_PATH, transaction_factory=_factory
    )
    assert set(result.keys()) == set(TABLE_NAMES), (
        f"guard_check обязан вернуть отпечаток всех {len(TABLE_NAMES)} таблиц, "
        f"вернул {sorted(result.keys())}"
    )
    for table in TABLE_NAMES:
        expected = [list(row) for row in MAPPING[table]]
        assert result[table] == expected, f"{table}: измеренное разошлось с эталоном молча"
    assert conn.trans_calls == len(TABLE_NAMES), (
        "по одной транзакции на таблицу — снят отпечаток каждой из девяти"
    )


@check(
    "(б) искажённый: один FIELD_TYPE одной колонки одной таблицы подменён — "
    "SchemaGuardMismatch, ни одна таблица не считается прочитанной"
)
def _t_mismatch():
    rows_by_table = _rows_from_mapping(MAPPING)
    target_table = TABLE_NAMES[0]
    original_row = list(rows_by_table[target_table][0])
    tampered_row = list(original_row)
    tampered_row[1] = (tampered_row[1] or 0) + 1  # FIELD_TYPE искажён на +1
    rows_by_table[target_table] = [tuple(tampered_row)] + rows_by_table[target_table][1:]

    conn = FakeConnection(rows_by_table)
    try:
        schema_guard.guard_check(
            conn, TABLE_NAMES, path=schema_guard.MAPPING_PATH, transaction_factory=_factory
        )
        raise AssertionError("подмена типа обязана дать SchemaGuardMismatch, а прошла молча")
    except schema_guard.SchemaGuardMismatch as exc:
        assert target_table in str(exc), f"отказ не назвал таблицу {target_table}: {exc}"


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
