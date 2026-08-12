"""
connector/agent/access_point.py — T-0-8, шаг 2

Единственная функция, через которую в проекте уходит любой SQL к базе PawnShop
(Firebird 2.5.9). Требование брифа `briefs/T-0-8.md` §«Шаг 2»: весь SQL к базе идёт
через эту функцию, других путей в проекте нет — это проверяется поиском по коду
(`grep -rn "fdb.connect\|\.execute(" --include=*.py`), а не заявлением.

Правило `ADR-048` (05_CONVENTIONS §I, «Правила наблюдения»): там, где предикат уже
реализован штатным механизмом платформы, проверка идёт этим механизмом, а не
собственным сравнением строк. Здесь предикат — «это оператор SELECT (или WITH …
SELECT), а не что-то ещё» — и он не проверяется поиском подстроки в тексте запроса.
Разбор оператора делает `sqlparse` (стандартная библиотека разбора SQL для Python,
используемая ради ЕЁ токенизатора, а не как второй самодельный парсер): она строит
разбор запроса и печатает ЕГО тип статистики (`Statement.get_type()`), различая
`SELECT`, `UPDATE`, `INSERT`, `DELETE`, `DROP`, `GRANT`, и т.д. по грамматике, а не по
наличию слова в тексте — поэтому слово «UPDATE» внутри комментария или строкового
литерала не превращает `SELECT`-запрос в отказ, а реальный `UPDATE`, замаскированный
переносами строк и регистром (`\n\n  uPdAtE ...`), распознаётся как `UPDATE` и
отбивается. Это же снимает главную проблему поиска подстроки: конструкция может быть
разнесена по строкам, и линейный grep её не поймает, а разбор — ловит.

Список разрешённых таблиц — девять таблиц из `briefs/T-0-5.md` §«Список таблиц» плюс
системные `RDB$*`/`MON$*` (guard схемы, ADR-004, и проверка режима транзакции —
ADR-037). Таблица вне списка → отказ ДО отправки на сервер, а не после.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any, Sequence

import sqlparse
from sqlparse.sql import Function, Identifier, IdentifierList
from sqlparse.tokens import CTE, Keyword, Wildcard

logger = logging.getLogger("lombard.agent.access_point")

# Источник — briefs/T-0-5.md §«Список таблиц» (девять таблиц, замерены и загранены).
# Понадобилась таблица вне этого списка → CONTEXT GAP архитектору, не догадка (00 §4).
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "CONTRACTS",
        "CONTRACTS_TERMS",
        "SUBJECTS",
        "CUSTOM_FIELDS_VALUES",
        "DIR_CUSTOM_FIELDS",
        "TABLES_TABLE",
        "CONTRACT_STATES",
        "DEPOSIT_TYPES",
        "OPERATIONS",
    }
)

_SYSTEM_PREFIXES = ("RDB$", "MON$")

_JOIN_KEYWORDS = {
    "FROM",
    "JOIN",
    "INNER JOIN",
    "LEFT JOIN",
    "RIGHT JOIN",
    "FULL JOIN",
    "LEFT OUTER JOIN",
    "RIGHT OUTER JOIN",
    "CROSS JOIN",
}


class AccessPointError(Exception):
    """Запрос отбит ДО отправки на сервер или транзакция не в ожидаемом режиме."""


@dataclass(frozen=True)
class _Verdict:
    ok: bool
    reason: str


def _single_statement(sql: str) -> sqlparse.sql.Statement:
    parsed = [s for s in sqlparse.parse(sql) if s.tokens]
    if len(parsed) == 0:
        raise AccessPointError("пустой запрос: sqlparse не нашёл ни одного оператора")
    if len(parsed) != 1:
        raise AccessPointError(
            f"запрос несёт {len(parsed)} операторов, а не один — "
            "составные запросы (несколько statements через ';') запрещены"
        )
    return parsed[0]


def _statement_type(stmt: sqlparse.sql.Statement) -> str:
    """Тип оператора — по разбору грамматики (sqlparse.Statement.get_type()),
    не по вхождению слова в текст (ADR-048)."""
    return stmt.get_type()


def _cte_names(stmt: sqlparse.sql.Statement) -> set[str]:
    """Имена, введённые `WITH <имя> AS (...)`: это алиасы, не таблицы БД, и на них
    белый список таблиц не распространяется — распространяется на то, что читают
    ВНУТРИ тела CTE (обходится тем же извлечением ниже, рекурсивно)."""
    names: set[str] = set()
    tokens = [t for t in stmt.tokens if not t.is_whitespace]
    for i, tok in enumerate(tokens):
        if tok.ttype is CTE and tok.value.upper() == "WITH":
            if i + 1 >= len(tokens):
                continue
            nxt = tokens[i + 1]
            if isinstance(nxt, IdentifierList):
                for ident in nxt.get_identifiers():
                    name = ident.get_real_name()
                    if name:
                        names.add(name.upper())
            elif isinstance(nxt, Identifier):
                name = nxt.get_real_name()
                if name:
                    names.add(name.upper())
    return names


def _extract_table_names(stmt: sqlparse.sql.Statement) -> set[str]:
    """Имена таблиц из FROM/JOIN, разобранные деревом токенов sqlparse, а не
    подстрокой. Работает рекурсивно, поэтому видит таблицы внутри тела CTE."""
    names: set[str] = set()

    def walk(token_list: sqlparse.sql.TokenList) -> None:
        expect_table = False
        for tok in token_list.tokens:
            if tok.is_whitespace:
                if expect_table:
                    continue
                continue
            if tok.ttype is Keyword and tok.value.upper() in _JOIN_KEYWORDS:
                expect_table = True
                continue
            if expect_table:
                if isinstance(tok, IdentifierList):
                    for ident in tok.get_identifiers():
                        real = ident.get_real_name()
                        if real:
                            names.add(real.upper())
                elif isinstance(tok, Identifier):
                    real = tok.get_real_name()
                    if real:
                        names.add(real.upper())
                expect_table = False
            if hasattr(tok, "tokens"):
                walk(tok)

    walk(stmt)
    return names


def _has_bare_wildcard(stmt: sqlparse.sql.Statement) -> bool:
    """`SELECT *` запрещён; `COUNT(*)` — легитимная агрегатная функция и не считается
    списком колонок, поэтому содержимое `Function(...)` в обход не проверяется."""

    def walk(tok: Any) -> bool:
        if isinstance(tok, Function):
            return False
        if tok.ttype is Wildcard:
            return True
        if hasattr(tok, "tokens"):
            return any(walk(t) for t in tok.tokens)
        return False

    return walk(stmt)


def validate_query(sql: str) -> _Verdict:
    """Разбирает запрос и возвращает вердикт БЕЗ обращения к серверу. Используется
    и самой `access_point`, и тестом `test_access_point.py` напрямую (логика белого
    списка не зависит от того, есть ли подключение к базе — требование шага 3)."""
    if not sql or not sql.strip():
        return _Verdict(False, "пустой текст запроса")

    try:
        stmt = _single_statement(sql)
    except AccessPointError as exc:
        return _Verdict(False, str(exc))

    stmt_type = _statement_type(stmt)
    if stmt_type != "SELECT":
        return _Verdict(
            False,
            f"запрещённый оператор: sqlparse определил тип '{stmt_type}', "
            "разрешён только SELECT (включая WITH … SELECT)",
        )

    if _has_bare_wildcard(stmt):
        return _Verdict(False, "SELECT * запрещён — требуется явный список колонок")

    cte_names = _cte_names(stmt)
    table_names = _extract_table_names(stmt) - cte_names
    forbidden = set()
    for name in table_names:
        if name in ALLOWED_TABLES:
            continue
        if any(name.startswith(prefix) for prefix in _SYSTEM_PREFIXES):
            continue
        forbidden.add(name)
    if forbidden:
        return _Verdict(
            False,
            "обращение к таблице вне разрешённого списка: "
            + ", ".join(sorted(forbidden)),
        )

    return _Verdict(True, "SELECT по разрешённым таблицам, явный список колонок")


def _read_only_transaction(connection: Any):
    """Открывает транзакцию только на чтение через штатный TPB-механизм драйвера
    (`fdb.TPB`, `access_mode = fdb.isc_tpb_read`), а не строкой `SET TRANSACTION` —
    тот же разрез ADR-048: используется механизм, который платформа даёт как
    предназначенный для этого, а не текстовая имитация."""
    import fdb  # локальный импорт: тест точки доступа (шаг 3) подключение подменяет

    tpb = fdb.TPB()
    tpb.access_mode = fdb.isc_tpb_read
    tpb.isolation_level = fdb.isc_tpb_read_committed
    tpb.lock_resolution = fdb.isc_tpb_wait
    tx = connection.trans(tpb)
    tx.begin()
    return tx


_MODE_CHECK_SQL = (
    "SELECT MON$READ_ONLY AS RO_FLAG "
    "FROM MON$TRANSACTIONS "
    "WHERE MON$TRANSACTION_ID = CURRENT_TRANSACTION"
)


def _assert_read_only(tx: Any) -> None:
    """Положительный факт режима транзакции (`ADR-037`, `05 §I`): читает признак
    режима из `MON$TRANSACTIONS` этой же транзакцией и падает, если он не тот.
    Отсутствие ошибки на предыдущих шагах фактом режима не считается."""
    cur = tx.cursor()
    cur.execute(_MODE_CHECK_SQL)
    row = cur.fetchone()
    cur.close()
    if row is None:
        raise AccessPointError(
            "проверка режима транзакции дала пустую выдачу при нулевом коде — "
            "это гэп наблюдения (05 §I), а не факт read-only; выполнение остановлено"
        )
    ro_flag = row[0]
    if ro_flag != 1:
        raise AccessPointError(
            f"транзакция НЕ в режиме read-only: MON$READ_ONLY={ro_flag!r} "
            "(ожидалось 1) — выполнение остановлено ДО запроса вызывающего кода"
        )
    logger.info("режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1")


def access_point(
    connection: Any,
    sql: str,
    params: Sequence[Any] = (),
    *,
    transaction_factory: Any = _read_only_transaction,
) -> list[tuple]:
    """Единственная функция доступа к базе PawnShop.

    Принимает текст запроса (и, опционально, параметры подстановки), возвращает
    строки результата. Ничего другого в базу не уходит: перед отправкой запрос
    ПОЛНОСТЬЮ проверяется `validate_query`, отказ бросает `AccessPointError` и
    соединения с сервером не происходит вовсе.

    Каждый вызов открывает СВОЮ транзакцию только на чтение (`transaction_factory`,
    по умолчанию `_read_only_transaction` — штатный TPB-механизм драйвера `fdb`) и
    подтверждает режим положительным фактом (`_assert_read_only`) ДО выполнения
    запроса вызывающего кода — отказ на этом шаге останавливает вызов, а не
    прогоняет запрос в непроверенном режиме.

    `transaction_factory` — единственная точка подмены для `test_access_point.py`
    (шаг 3 брифа: «подключение подменяется», к базе клиента тест не обращается).
    Логика белого списка (`validate_query`) при этом ни к транзакции, ни к
    подключению не обращается вовсе — она отработала строкой выше, до этого места.
    """
    verdict = validate_query(sql)
    if not verdict.ok:
        raise AccessPointError(verdict.reason)

    logger.info(
        "SQL к PawnShop [%s]: %s",
        datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        sql,
    )

    tx = transaction_factory(connection)
    try:
        _assert_read_only(tx)
        cur = tx.cursor()
        cur.execute(sql, params) if params else cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        tx.commit()
        return rows
    except Exception:
        tx.rollback()
        raise
