"""
connector/agent/test_access_point.py — T-0-8, шаг 3

Тест единственной точки доступа `access_point.py`. Гоняется на нашей стороне, к базе
клиента не подключаясь: подключение и открытие транзакции подменяются фиктивными
объектами (`FakeConnection`/`FakeTransaction`/`FakeCursor`, ниже). Логика белого
списка (`validate_query`) не зависит от того, есть ли база вообще — она отрабатывает
до всякого обращения к соединению.

Приёмка требует ОБЕИХ сторон каждой проверки (`ADR-033`, «проба обязана различать
исходы»), поэтому пары «проходит / отбивается» держатся в одном тесте намеренно, а не
разносятся по файлам, где потерялась бы контрастность.

Запуск: `python3 -m connector.agent.test_access_point` из корня репозитория —
печатает `провалено N`; `провалено 0` и есть вердикт (правило наблюдения `05 §I`:
вердикт печатает совпавшие строки/счётчики, а не метку).
"""

from __future__ import annotations

import sys
import traceback
from typing import Any, Sequence

from connector.agent.access_point import AccessPointError, access_point, validate_query

# ---------------------------------------------------------------------------
# Фиктивные соединение/транзакция/курсор — заменяют fdb, к серверу не обращаются.
# ---------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, ro_flag: int, rows: list[tuple]):
        self._ro_flag = ro_flag
        self._rows = rows
        self._last_result: list[tuple] | None = None
        self.executed: list[str] = []

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self.executed.append(sql)
        if "MON$TRANSACTIONS" in sql and "MON$READ_ONLY" in sql:
            self._last_result = [(self._ro_flag,)]
        else:
            self._last_result = list(self._rows)

    def fetchone(self):
        return self._last_result[0] if self._last_result else None

    def fetchall(self):
        return list(self._last_result or [])

    def close(self) -> None:
        pass


class FakeTransaction:
    def __init__(self, ro_flag: int, rows: list[tuple]):
        self._ro_flag = ro_flag
        self._rows = rows
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._ro_flag, self._rows)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeConnection:
    """Подмена подключения. `trans_calls` считает, сколько раз к ней в принципе
    обращались — используется, чтобы доказать: запрещённый оператор отбивается
    ДО обращения к соединению, а не после неудачной попытки исполнить его."""

    def __init__(self, ro_flag: int = 1, rows: list[tuple] | None = None):
        self.ro_flag = ro_flag
        self.rows = rows or [(1, "СЫРЬЁ")]
        self.trans_calls = 0

    def open_transaction(self) -> FakeTransaction:
        self.trans_calls += 1
        return FakeTransaction(self.ro_flag, self.rows)


def _factory(connection: FakeConnection) -> FakeTransaction:
    return connection.open_transaction()


# ---------------------------------------------------------------------------
# Реестр проверок: (имя, функция). Каждая либо ничего не бросает (успех),
# либо намеренно кидает AssertionError с сообщением — печатается как провал.
# ---------------------------------------------------------------------------

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


@check("1a: разрешённый SELECT по разрешённой таблице — проходит и возвращает строки")
def _t1a():
    conn = FakeConnection(ro_flag=1, rows=[(1, "A"), (2, "B")])
    rows = access_point(
        conn,
        "SELECT ID, NAME FROM CONTRACTS",
        transaction_factory=_factory,
    )
    assert rows == [(1, "A"), (2, "B")], f"неожиданные строки: {rows!r}"
    assert conn.trans_calls == 1, "разрешённый запрос обязан дойти до транзакции ровно один раз"


@check("1b: разрешённый SELECT по RDB$ (метаданные guard схемы) — проходит")
def _t1b():
    conn = FakeConnection(ro_flag=1, rows=[("CONTRACT_ID", "INTEGER")])
    rows = access_point(
        conn,
        "SELECT RDB$FIELD_NAME, RDB$FIELD_TYPE FROM RDB$RELATION_FIELDS "
        "WHERE RDB$RELATION_NAME = 'CONTRACTS'",
        transaction_factory=_factory,
    )
    assert rows == [("CONTRACT_ID", "INTEGER")]


@check("2a: UPDATE — отбивается исключением ДО обращения к соединению")
def _t2a():
    conn = FakeConnection()
    try:
        access_point(conn, "UPDATE CONTRACTS SET ID = ID WHERE 1 = 0", transaction_factory=_factory)
        raise AssertionError("UPDATE обязан быть отбит, а прошёл")
    except AccessPointError:
        pass
    assert conn.trans_calls == 0, "запрещённый оператор дошёл до соединения — это дефект контроля"


@check("2b: INSERT — отбивается исключением")
def _t2b():
    conn = FakeConnection()
    try:
        access_point(conn, "INSERT INTO CONTRACTS (ID) VALUES (1)", transaction_factory=_factory)
        raise AssertionError("INSERT обязан быть отбит, а прошёл")
    except AccessPointError:
        pass
    assert conn.trans_calls == 0


@check("2c: DELETE — отбивается исключением")
def _t2c():
    conn = FakeConnection()
    try:
        access_point(conn, "DELETE FROM CONTRACTS", transaction_factory=_factory)
        raise AssertionError("DELETE обязан быть отбит, а прошёл")
    except AccessPointError:
        pass
    assert conn.trans_calls == 0


@check("2d: DROP — отбивается исключением")
def _t2d():
    conn = FakeConnection()
    try:
        access_point(conn, "DROP TABLE CONTRACTS", transaction_factory=_factory)
        raise AssertionError("DROP обязан быть отбит, а прошёл")
    except AccessPointError:
        pass
    assert conn.trans_calls == 0


@check("2e: GRANT — отбивается исключением")
def _t2e():
    conn = FakeConnection()
    try:
        access_point(conn, "GRANT SELECT ON CONTRACTS TO PUBLIC", transaction_factory=_factory)
        raise AssertionError("GRANT обязан быть отбит, а прошёл")
    except AccessPointError:
        pass
    assert conn.trans_calls == 0


@check("2f: EXECUTE BLOCK — отбивается исключением")
def _t2f():
    conn = FakeConnection()
    try:
        access_point(
            conn,
            "EXECUTE BLOCK AS BEGIN UPDATE CONTRACTS SET ID = ID; END",
            transaction_factory=_factory,
        )
        raise AssertionError("EXECUTE BLOCK обязан быть отбит, а прошёл")
    except AccessPointError:
        pass
    assert conn.trans_calls == 0


@check(
    "3: SELECT с запрещённым словом внутри КОММЕНТАРИЯ — проходит "
    "(доказывает разбор оператора, а не поиск подстроки, ADR-048)"
)
def _t3_comment():
    conn = FakeConnection(ro_flag=1, rows=[(1,)])
    rows = access_point(
        conn,
        "-- UPDATE и DROP TABLE упомянуты тут, но это комментарий\n"
        "SELECT ID FROM CONTRACTS",
        transaction_factory=_factory,
    )
    assert rows == [(1,)]


@check(
    "3-БИС: SELECT с запрещённым словом внутри СТРОКОВОГО ЛИТЕРАЛА — проходит"
)
def _t3_literal():
    conn = FakeConnection(ro_flag=1, rows=[("UPDATE DROP GRANT",)])
    rows = access_point(
        conn,
        "SELECT 'UPDATE DROP GRANT' AS LITERAL_TEXT FROM CONTRACTS",
        transaction_factory=_factory,
    )
    assert rows == [("UPDATE DROP GRANT",)]


@check(
    "4: UPDATE, замаскированный переносами строк и регистром, — отбивается"
)
def _t4_masked():
    conn = FakeConnection()
    masked = "\n\n  uPd\nAtE CONTRACTS\nSET ID = ID WHERE 1=0"
    verdict = validate_query(masked)
    assert not verdict.ok, f"маскированный UPDATE прошёл валидацию: {verdict!r}"
    try:
        access_point(conn, masked, transaction_factory=_factory)
        raise AssertionError("маскированный UPDATE обязан быть отбит, а прошёл")
    except AccessPointError:
        pass
    assert conn.trans_calls == 0


@check("5: обращение к таблице вне девяти разрешённых — отбивается")
def _t5_table():
    conn = FakeConnection()
    try:
        access_point(conn, "SELECT ID FROM SOME_VENDOR_TABLE", transaction_factory=_factory)
        raise AssertionError("запрос к неразрешённой таблице обязан быть отбит, а прошёл")
    except AccessPointError as exc:
        assert "SOME_VENDOR_TABLE" in str(exc), f"отказ не назвал таблицу: {exc}"
    assert conn.trans_calls == 0


@check(
    "5-БИС: разрешённая таблица среди девяти, для контраста с проверкой 5 "
    "(положительный контроль различимости — ADR-033)"
)
def _t5bis_positive_control():
    conn = FakeConnection(ro_flag=1, rows=[(1,)])
    rows = access_point(conn, "SELECT ID FROM OPERATIONS", transaction_factory=_factory)
    assert rows == [(1,)]


@check(
    "6: попытка работы при режиме транзакции НЕ read-only — отбивается "
    "(положительный факт MON$READ_ONLY, а не отсутствие ошибки, ADR-037)"
)
def _t6_not_readonly():
    conn = FakeConnection(ro_flag=0, rows=[(1,)])  # разрешённый SELECT, но режим не тот
    try:
        access_point(conn, "SELECT ID FROM CONTRACTS", transaction_factory=_factory)
        raise AssertionError("запрос в НЕ read-only транзакции обязан быть отбит, а прошёл")
    except AccessPointError as exc:
        assert "read-only" in str(exc) or "READ_ONLY" in str(exc), (
            f"отказ пришёл не по режиму транзакции: {exc}"
        )


@check(
    "6-БИС: та же таблица и запрос при режиме read-only=1 — проходит "
    "(положительный контроль для проверки 6, ADR-033)"
)
def _t6bis_positive_control():
    conn = FakeConnection(ro_flag=1, rows=[(1,)])
    rows = access_point(conn, "SELECT ID FROM CONTRACTS", transaction_factory=_factory)
    assert rows == [(1,)]


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
