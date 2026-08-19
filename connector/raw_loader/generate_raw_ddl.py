"""
connector/generate_raw_ddl.py — T-1-1, шаг 1

Чистая функция: девять таблиц слоя сырья `raw_*` датасета `lombard_ops`
ГЕНЕРИРУЮТСЯ из `connector/mapping.json` → `schema_fingerprint`
(9 таблиц / 124 колонки, `T-0-10`), не пишутся от руки (`ADR-083` п.3–4,
`02_DATA_CONTRACTS.md §2`).

Правило типов — закрытый список семи кодов Firebird (`ADR-083` п.4):

    7  SMALLINT           -> INT64
    8  INTEGER             -> INT64
    12 DATE                -> DATE
    16 BIGINT/NUMERIC      -> INT64 при scale = 0, NUMERIC при scale < 0
    27 DOUBLE PRECISION    -> FLOAT64
    35 TIMESTAMP           -> TIMESTAMP
    37 VARCHAR             -> STRING

Код типа вне этого списка — `UnknownTypeCode`, с именем таблицы, колонки и
кода: стоп-условие, не «похожий тип» (05 §I, anti-improvisation).

Каждая сгенерированная таблица дополнительно несёт `loaded_at TIMESTAMP
NOT NULL` и `source_blob STRING NOT NULL` (ADR-083 п.4) — без них прогон
неотличим от предыдущего.

Без сети, без BigQuery — чистая функция над уже прочитанным словарём
`schema_fingerprint` (или путём к `mapping.json`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAPPING_PATH = Path(__file__).resolve().parent / "mapping.json"
DDL_OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "sql" / "ddl" / "lombard_ops_raw.sql"
)

# Закрытый список кодов типов Firebird -> BigQuery (ADR-083 п.4). Код вне
# этого множества поднимает UnknownTypeCode — не подставляется "похожий тип".
_SIMPLE_TYPE_MAP: dict[int, str] = {
    7: "INT64",
    8: "INT64",
    12: "DATE",
    27: "FLOAT64",
    35: "TIMESTAMP",
    37: "STRING",
}

class UnknownTypeCode(ValueError):
    """Код типа колонки вне закрытого списка ADR-083 п.4 — стоп, не «похожий тип»."""

    def __init__(self, table: str, column: str, code: int):
        self.table = table
        self.column = column
        self.code = code
        super().__init__(
            f"UnknownTypeCode: таблица {table}, колонка {column}, код типа {code} "
            "вне закрытого списка ADR-083 п.4 (7, 8, 12, 16, 27, 35, 37) — "
            "изменение схемы вендора, стоп, не подстановка похожего типа"
        )


def raw_table_name(firebird_table: str) -> str:
    """`CONTRACTS_TERMS` -> `raw_contracts_terms` (ADR-083 п.3)."""
    return f"raw_{firebird_table.lower()}"


def bq_type_for_column(table: str, column: str, code: int, scale: int) -> str:
    """Один код типа Firebird -> один тип BigQuery, закрытым списком.
    `code == 16` различается по `scale`: `scale == 0` -> `INT64` (BIGINT),
    `scale < 0` -> `NUMERIC` (масштабированное число, ADR-083 п.4)."""
    if code == 16:
        return "INT64" if scale == 0 else "NUMERIC"
    if code in _SIMPLE_TYPE_MAP:
        return _SIMPLE_TYPE_MAP[code]
    raise UnknownTypeCode(table, column, code)


def load_schema_fingerprint(mapping: dict[str, Any] | Path | str) -> dict[str, list[list[Any]]]:
    """Принимает либо уже распарсенный `mapping.json` (dict с ключом
    `schema_fingerprint`), либо путь к файлу на диске."""
    if isinstance(mapping, (Path, str)):
        path = Path(mapping)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = mapping
    fingerprint = data.get("schema_fingerprint")
    if not isinstance(fingerprint, dict):
        raise ValueError(
            "CONTEXT GAP: mapping.json не несёт раздел schema_fingerprint — "
            "источник истины слоя сырья отсутствует"
        )
    return fingerprint


def table_schema_fields(table: str, columns: list[list[Any]]) -> list[tuple[str, str, str]]:
    """Ожидаемая схема таблицы `raw_<table>` как список `(имя, тип, mode)` —
    тот же вид, что принимает guard шага 2 (`connector/raw_loader/guard.py`)
    и `bigquery.SchemaField`. Порядок — отпечаток, затем две служебные
    колонки (`loaded_at`, `source_blob`), обе `REQUIRED`; остальные
    `NULLABLE` (отпечаток Firebird не несёт NOT NULL-ограничений колонок
    пользовательских таблиц вне двух служебных)."""
    fields: list[tuple[str, str, str]] = []
    for column in columns:
        name, code, _length, scale = column
        bq_type = bq_type_for_column(table, name, code, scale)
        fields.append((name.lower(), bq_type, "NULLABLE"))
    fields.append(("loaded_at", "TIMESTAMP", "REQUIRED"))
    fields.append(("source_blob", "STRING", "REQUIRED"))
    return fields


def generate_table_ddl(table: str, columns: list[list[Any]]) -> str:
    """`CREATE TABLE IF NOT EXISTS lombard_ops.raw_<table> (...)` — одна
    таблица, колонки в порядке отпечатка плюс две служебные."""
    lines: list[str] = []
    for name, bq_type, mode in table_schema_fields(table, columns):
        suffix = " NOT NULL" if mode == "REQUIRED" else ""
        lines.append(f"  {name} {bq_type}{suffix}")
    columns_sql = ",\n".join(lines)
    return (
        f"CREATE TABLE IF NOT EXISTS `lombard_ops.{raw_table_name(table)}` (\n"
        f"{columns_sql}\n"
        ");"
    )


def generate_raw_ddl(mapping: dict[str, Any] | Path | str) -> str:
    """DDL девяти таблиц `raw_*`, в порядке таблиц отпечатка. Заголовок
    называет источник и правило (ADR-083), тем же стилем, что
    `sql/ddl/lombard_ops.sql`."""
    fingerprint = load_schema_fingerprint(mapping)
    header = (
        "-- T-1-1 · DDL слоя сырья lombard_ops (europe-west3)\n"
        "-- ГЕНЕРИРУЕТСЯ из connector/mapping.json -> schema_fingerprint (T-0-10),\n"
        "-- не пишется от руки (ADR-083 п.3-4). Правило типов — закрытый список\n"
        "-- семи кодов Firebird; код вне списка стопит генератор (UnknownTypeCode).\n"
        "-- Источник истины: 02_DATA_CONTRACTS.md §2. Не редактировать руками —\n"
        "-- перегенерировать: python3 connector/generate_raw_ddl.py\n"
    )
    tables_sql = "\n\n".join(
        generate_table_ddl(table, columns) for table, columns in fingerprint.items()
    )
    return header + "\n" + tables_sql + "\n"


def write_raw_ddl(
    mapping: dict[str, Any] | Path | str = MAPPING_PATH,
    output_path: Path = DDL_OUTPUT_PATH,
) -> Path:
    """Генерирует DDL и печатает его в `sql/ddl/lombard_ops_raw.sql` — сайд-эффект,
    вызывается точкой входа `__main__`, не тестами (тесты держатся на чистой
    `generate_raw_ddl`)."""
    ddl = generate_raw_ddl(mapping)
    output_path.write_text(ddl, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    path = write_raw_ddl()
    print(f"DDL девяти таблиц raw_* сгенерирован: {path}")
