"""
connector/agent/schema_guard.py — T-0-8, шаг 4

Guard схемы Firebird (`ADR-004`, `00 §3-БИС(c)`): перед чтением каждой из девяти
разрешённых таблиц снимается отпечаток метаданных (имена и типы колонок, взятые из
`RDB$RELATION_FIELDS`/`RDB$FIELDS` — САМОЙ базы, а не из головы) и сверяется с
эталоном. Расхождение → **стоп и алерт, не искажение** (`00 §3-БИС(c)`, не смягчать
до предупреждения).

Отпечаток решает и вторую задачу: явный список колонок для `SELECT` строится из него
же (`schema_guard.column_names(fingerprint)`), поэтому агент нигде не угадывает имена
колонок — они получены тем же измерением, что и отпечаток, а не подставлены руками.
`SELECT *` благодаря этому не нужен ни для чтения данных, ни для самого отпечатка:
запрос к `RDB$RELATION_FIELDS` тоже идёт явным списком колонок (см. `_FINGERPRINT_SQL`).

Эталон отпечатка на входе задачи может отсутствовать: `connector/mapping.json`
заводится задачей `T-0-10`, не этой. Пока его нет, эталон живёт в
`connector/agent/schema_fingerprint.json` — файле ЭТОЙ задачи. **Первый прогон
создаёт отпечаток и печатает его, сверка включается со второго** — это записывается
логом явно, а не обходится молча (требование шага 4 брифа `T-0-8`). Когда `T-0-10`
заведёт `connector/mapping.json` с разделом `schema_fingerprint`, источник эталона
переключается решением, а не этим модулем тихо.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from connector.agent.access_point import access_point

logger = logging.getLogger("lombard.agent.schema_guard")

DEFAULT_FINGERPRINT_PATH = Path(__file__).with_name("schema_fingerprint.json")


class SchemaGuardMismatch(Exception):
    """Отпечаток разошёлся с эталоном. Стоп и алерт (00 §3-БИС(c)) — не искажение,
    не молчаливое продолжение с расхождением."""


# Явный список колонок системной таблицы — тот же принцип, что и у пользовательских
# таблиц: SELECT * здесь тоже не используется.
_FINGERPRINT_SQL = (
    "SELECT f.RDB$FIELD_NAME AS COLUMN_NAME, "
    "t.RDB$FIELD_TYPE AS FIELD_TYPE, "
    "t.RDB$FIELD_LENGTH AS FIELD_LENGTH, "
    "t.RDB$FIELD_SCALE AS FIELD_SCALE "
    "FROM RDB$RELATION_FIELDS f "
    "JOIN RDB$FIELDS t ON t.RDB$FIELD_NAME = f.RDB$FIELD_SOURCE "
    "WHERE f.RDB$RELATION_NAME = ? "
    "ORDER BY f.RDB$FIELD_POSITION"
)


def _clean(value: Any) -> Any:
    """Firebird CHAR-поля системных таблиц приходят с хвостовыми пробелами —
    это особенность формата колонки, не наше решение о данных."""
    if isinstance(value, str):
        return value.strip()
    return value


def fingerprint_table(connection: Any, table_name: str) -> list[list[Any]]:
    """Снимает отпечаток одной таблицы через `access_point` — тот же контролируемый
    путь, что и для данных, никакого отдельного бэкдора к метаданным нет."""
    rows = access_point(connection, _FINGERPRINT_SQL, (table_name,))
    fingerprint = [[_clean(v) for v in row] for row in rows]
    if not fingerprint:
        raise SchemaGuardMismatch(
            f"пустой отпечаток таблицы {table_name} при нулевом коде — "
            "гэп наблюдения (05 §I), а не факт «таблицы нет»; таблица разрешена "
            "белым списком access_point, значит доступна — расхождение подозрительно"
        )
    return fingerprint


def column_names(fingerprint: list[list[Any]]) -> list[str]:
    """Явный список колонок для SELECT — построен из отпечатка, не придуман."""
    return [row[0] for row in fingerprint]


def load_reference(path: Path = DEFAULT_FINGERPRINT_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_reference(data: dict[str, Any], path: Path = DEFAULT_FINGERPRINT_PATH) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def guard_check(
    connection: Any,
    table_names: list[str],
    path: Path = DEFAULT_FINGERPRINT_PATH,
) -> dict[str, list[list[Any]]]:
    """Снимает отпечаток КАЖДОЙ разрешённой таблицы и сверяет с эталоном.

    Эталона нет (первый прогон) → отпечаток СОЗДАЁТСЯ, печатается целиком и
    записывается как эталон; сверка со второго прогона — это состояние логируется
    явным словом, не тихим прохождением.
    Эталон есть и совпал → чтение разрешено.
    Эталон есть и разошёлся → `SchemaGuardMismatch`, чтение НЕ выполняется вообще —
    ни для одной из девяти таблиц, даже для тех, что совпали: расхождение схемы
    ставит под сомнение весь снимок, а не одну таблицу.
    """
    measured = {t: fingerprint_table(connection, t) for t in table_names}

    reference = load_reference(path)
    if reference is None:
        logger.warning(
            "GUARD: эталон отпечатка отсутствует (%s) — ПЕРВЫЙ ПРОГОН создаёт его. "
            "Сверка схемы включается со следующего прогона, не с этого.",
            path,
        )
        for table, fp in measured.items():
            logger.info("GUARD: создан отпечаток %s: %s", table, fp)
        save_reference(measured, path)
        return measured

    mismatches: dict[str, tuple[list[Any], list[Any]]] = {}
    for table in table_names:
        if reference.get(table) != measured[table]:
            mismatches[table] = (reference.get(table), measured[table])

    if mismatches:
        for table, (ref, cur) in mismatches.items():
            logger.error(
                "GUARD MISMATCH %s: эталон=%s ИЗМЕРЕНО=%s", table, ref, cur
            )
        raise SchemaGuardMismatch(
            f"расхождение отпечатка схемы на {len(mismatches)} таблиц(е): "
            f"{sorted(mismatches)} — чтение остановлено, эталон НЕ обновлён"
        )

    logger.info("GUARD: отпечаток всех %d таблиц совпал с эталоном", len(table_names))
    return measured
