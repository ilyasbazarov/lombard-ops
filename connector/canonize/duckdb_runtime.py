"""
connector/canonize/duckdb_runtime.py — T-1-2a

Загружает `sql/canonization.sql` (действующий текст BigQuery Standard SQL) и
исполняет его БУКВАЛЬНОЙ ЛОГИКОЙ на локальном движке DuckDB поверх фикстур —
без единого обращения к BigQuery. Это НЕ переписывание бизнес-логики на
Python (запрещённый класс ошибки, `05_CONVENTIONS.md`, «Штатный механизм
платформы бьёт самодельное сравнение строк», ADR-048): SQL-текст один и тот
же файл, один и тот же исполнитель запросов (реальный SQL-движок), различие
между BigQuery и DuckDB — только СИНТАКСИС квотирования и ОДНА функция даты
(`DATE_DIFF`, разный порядок аргументов у двух диалектов на одну и ту же
величину). Три адаптации ниже — единственные, весь список исчерпывающий:

1. Обратные кавычки вокруг `dataset.table`/`dataset.function` убираются —
   DuckDB не поддерживает backtick-квотирование дословно, схема `lombard_ops`
   создаётся тестом и делает `dataset.table` валидным неквотированным путём
   в обоих диалектах.
2. `SELECT * EXCEPT(col)` (BigQuery) -> `SELECT * EXCLUDE(col)` (DuckDB) —
   тот же предикат «все колонки, кроме», разное ключевое слово (`EXCEPT` в
   DuckDB зарезервировано под операцию над множествами строк).
3. `CREATE OR REPLACE FUNCTION` -> `CREATE OR REPLACE MACRO`, и ровно один
   вызов `DATE_DIFF(today, due_date, DAY)` (BigQuery: результат = today −
   due_date) переписывается в `DATE_DIFF('day', due_date, today)` (DuckDB:
   `date_diff(part, startdate, enddate)` = enddate − startdate) — та же
   разность, доказано числом ниже в тестах (шаг 8, `offset_days` сверяется
   построчно).

Ничего из бизнес-правил (пороги статуса, ветви детектора продлений,
дедупликация снапшота) в этом файле не переписывается — они читаются из
`sql/canonization.sql` как есть и исполняются DuckDB.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONIZATION_SQL_PATH = REPO_ROOT / "sql" / "canonization.sql"

_DATE_DIFF_PATTERN = re.compile(
    r"DATE_DIFF\(\s*today\s*,\s*due_date\s*,\s*DAY\s*\)"
)


def _strip_line_comments(text: str) -> str:
    """Убирает `-- ...` до конца строки. В файле нет `--` внутри строковых
    литералов, построчное удаление безопасно."""
    out_lines = []
    for line in text.splitlines():
        idx = line.find("--")
        out_lines.append(line[:idx] if idx != -1 else line)
    return "\n".join(out_lines)


def translate_to_duckdb(sql_text: str) -> str:
    """Три адаптации синтаксиса, описанные в докстринге модуля. Логика не
    меняется — меняется квотирование и порядок аргументов одной функции."""
    text = _strip_line_comments(sql_text)
    text = text.replace("`", "")
    text = text.replace("CREATE OR REPLACE FUNCTION", "CREATE OR REPLACE MACRO")
    text = text.replace("EXCEPT(", "EXCLUDE(")
    text = _DATE_DIFF_PATTERN.sub("DATE_DIFF('day', due_date, today)", text)
    return text


def load_canonization_sql() -> str:
    if not CANONIZATION_SQL_PATH.exists():
        raise FileNotFoundError(
            f"CONTEXT GAP: {CANONIZATION_SQL_PATH} не найден"
        )
    return CANONIZATION_SQL_PATH.read_text(encoding="utf-8")


def statements(sql_text: str) -> list[str]:
    return [s.strip() for s in sql_text.split(";") if s.strip()]


# Схема сырья для теста — подмножество колонок sql/ddl/lombard_ops_raw.sql,
# ровно те, что канонизация читает (02_DATA_CONTRACTS.md §2/§3).
_RAW_DDL = {
    "raw_contracts": """
        contract_id INT64,
        contract_state INT64,
        contract_date DATE,
        id_prev_contract INT64,
        plan_close_date DATE,
        loaded_at TIMESTAMP,
        source_blob STRING
    """,
    "raw_contract_states": """
        state_id INT64,
        code STRING,
        sort_order INT64,
        loaded_at TIMESTAMP,
        source_blob STRING
    """,
    "raw_operations": """
        op_id INT64,
        deposit_id INT64,
        op_vid INT64,
        op_date DATE,
        loaded_at TIMESTAMP,
        source_blob STRING
    """,
}


def new_connection() -> duckdb.DuckDBPyConnection:
    """Пустая in-memory база с пустой схемой сырья lombard_ops — без данных.
    Данные заводит каждый тест своей фикстурой (connector/canonize/fixtures.py)."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA lombard_ops;")
    for table, columns in _RAW_DDL.items():
        con.execute(f"CREATE TABLE lombard_ops.{table} ({columns});")
    return con


def apply_canonization_views(con: duckdb.DuckDBPyConnection) -> None:
    """Исполняет sql/canonization.sql (переведённый под DuckDB) целиком —
    создаёт все VIEW/MACRO шагов 1-7 канонизации на текущем соединении."""
    sql_text = load_canonization_sql()
    translated = translate_to_duckdb(sql_text)
    for stmt in statements(translated):
        con.execute(stmt + ";")
