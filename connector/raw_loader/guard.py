"""
connector/raw_loader/guard.py — T-1-1, шаг 2

Guard схемы НА ЗАГРУЗКЕ (`01_ARCHITECTURE.md §3` называет ДРУГОЙ guard — на
стороне агента, ПЕРЕД чтением Firebird; этот guard сверяет ДОСТАВЛЕННУЮ в
GCS структуру с ЖИВОЙ схемой таблицы `raw_*` в BigQuery — тот же эталон
`connector/mapping.json`, две разные точки проверки, не дублирование).

Сверка — множество пар `(имя, тип)`, порядок не важен. Расхождение поднимает
`SchemaLoadGuardMismatch` с именем таблицы и ОБЕИМИ сторонами сравнения
(эталон/измерено), тем же стилем сообщения, что
`connector.agent.schema_guard.SchemaGuardMismatch` (00 §3-БИС(c): стоп и
алерт, не искажение).

Живая схема BigQuery читается через `bigquery.Client.get_table(table_ref).schema`,
за подменяемой фабрикой клиента — тот же приём, что
`functions/cf_daily/bq_loader._default_bq_client_factory`, тестируется на моке,
без сети.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable


class SchemaLoadGuardMismatch(Exception):
    """Ожидаемая схема (эталон mapping.json) разошлась с живой схемой BigQuery
    на загрузке. Стоп, чтение/загрузка этой таблицы не выполняется
    (00 §3-БИС(c)) — расхождение схемы ставит под сомнение весь снимок, не
    искажается тихо."""

    def __init__(self, table: str, expected: set[tuple[str, str]], actual: set[tuple[str, str]]):
        self.table = table
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"SchemaLoadGuardMismatch: таблица {table} — эталон={sorted(expected)} "
            f"ИЗМЕРЕНО={sorted(actual)} — загрузка ОСТАНОВЛЕНА"
        )


def _default_bq_client_factory(project_id: str | None) -> Any:
    from google.cloud import bigquery  # type: ignore

    return bigquery.Client(project=project_id)


def expected_schema_pairs(schema: Iterable[tuple[str, str, str]]) -> set[tuple[str, str]]:
    """`(имя, тип, mode)` (шаг 1, generate_raw_ddl) -> множество `(имя, тип)`
    для сверки — `mode` (NOT NULL/NULLABLE) в сверку guard'а не входит: guard
    ловит дрейф СОСТАВА и ТИПА колонок, не nullability."""
    return {(name.lower(), field_type) for name, field_type, _mode in schema}


_LEGACY_SQL_TO_STANDARD_SQL = {
    # `bigquery.Client.get_table(...).schema` возвращает `field_type` именами
    # legacy SQL, даже для таблиц, созданных standard-SQL DDL (`INT64` и т.д.)
    # — замерено первым реальным прогоном шага 10 (`SchemaLoadGuardMismatch`
    # на `raw_contracts`, эталон нёс `INT64`, живая схема — `INTEGER`).
    # Список — ровно типы закрытого списка `ADR-083` п.4, не шире.
    "INTEGER": "INT64",
    "FLOAT": "FLOAT64",
}


def live_schema_pairs(bq_schema: Iterable[Any]) -> set[tuple[str, str]]:
    """Живая схема из `bigquery.Client.get_table(...).schema` (список
    `SchemaField`, каждый несёт `.name`/`.field_type`) -> то же множество пар,
    для сверки тем же ключом, что и эталон. `field_type` нормализуется к
    standard SQL — см. `_LEGACY_SQL_TO_STANDARD_SQL`."""
    return {
        (field.name.lower(), _LEGACY_SQL_TO_STANDARD_SQL.get(field.field_type, field.field_type))
        for field in bq_schema
    }


def check_schema(
    table: str,
    expected_schema: Iterable[tuple[str, str, str]],
    *,
    dataset: str = "lombard_ops",
    project_id: str | None = None,
    client_factory: Callable[[str | None], Any] = _default_bq_client_factory,
) -> None:
    """Guard одной таблицы: читает живую схему `dataset.table` из BigQuery и
    сверяет с ожидаемой (шаг 1). Совпало — тихо возвращает `None`. Разошлось —
    `SchemaLoadGuardMismatch` с обеими сторонами."""
    client = client_factory(project_id)
    table_ref = f"{project_id}.{dataset}.{table}" if project_id else f"{dataset}.{table}"
    live_table = client.get_table(table_ref)

    expected = expected_schema_pairs(expected_schema)
    actual = live_schema_pairs(live_table.schema)

    if expected != actual:
        raise SchemaLoadGuardMismatch(table, expected, actual)
