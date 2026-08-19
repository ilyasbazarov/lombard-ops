"""
connector/canonize/test_canonization.py — T-1-2a

Офлайн-тест `sql/canonization.sql` на фикстурах слоя сырья, БЕЗ единого
обращения к BigQuery и без единого обращения к базе клиента (Firebird).
SQL исполняется реальным движком DuckDB поверх переведённого текста
(`connector/canonize/duckdb_runtime.py` — три точечные адаптации синтаксиса,
логика не переписывается).

**Объект замера определён:** фикстуры слоя сырья, построены этой сессией —
не читались нигде ранее (`ADR-063` R2).

Запуск: `python3 connector/canonize/test_canonization.py` из корня репозитория.
Зависимость теста (НЕ прод-зависимость — `duckdb` нигде не деплоится, только
локальный движок для офлайн-прогона): `pip3 install --user duckdb` (версия
на момент сессии — 1.4.5).
"""

from __future__ import annotations

import datetime
import re
import sys
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "functions" / "cf_daily"))

from duckdb_runtime import apply_canonization_views, new_connection  # noqa: E402
from fixtures import (  # noqa: E402
    ANCHOR_DUE_DATE,
    STATE_CLOSED,
    STATE_OPEN,
    insert_contract,
    insert_operation,
    seed_contract_states,
)
from status import compute_status  # noqa: E402

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


# ---------------------------------------------------------------------------
# Шаг 1 · status_raw
# ---------------------------------------------------------------------------


@check("шаг 1: status_raw через CONTRACT_STATE -> CONTRACT_STATES.code, фикстура 3 договора")
def _t1_status_raw():
    con = new_connection()
    seed_contract_states(con)
    insert_contract(con, contract_id=1, contract_state=STATE_OPEN,
                     contract_date="2026-07-01", plan_close_date="2026-07-30")
    insert_contract(con, contract_id=2, contract_state=STATE_CLOSED,
                     contract_date="2026-06-01", plan_close_date="2026-06-30")
    insert_contract(con, contract_id=3, contract_state=STATE_OPEN,
                     contract_date="2026-05-01", plan_close_date="2026-05-30")
    apply_canonization_views(con)
    rows = con.execute(
        "SELECT contract_id, status_raw FROM lombard_ops.v_status_raw ORDER BY contract_id"
    ).fetchall()
    assert rows == [(1, "OPEN"), (2, "CLOSED"), (3, "OPEN")], rows


# ---------------------------------------------------------------------------
# Шаг 2-4 · детектор продлений — обе ветви + объединение, три счёта на одной
# фикстуре (критерий приёмки: ответ известен по построению).
#
# Фикстура (6 договоров, contract_state = OPEN у всех, чтобы участвовать в
# canonical view тоже):
#   1 — id_prev_contract NULL, без операций OP_VID=0     -> ни одна ветвь
#   2 — id_prev_contract = 1, без операций OP_VID=0       -> только «Переоткрытие»
#   3 — id_prev_contract NULL, одна операция OP_VID=0     -> только «Погашение»
#   4 — id_prev_contract = 2, ДВЕ операции OP_VID=0        -> ОБЕ ветви разом (OR не задваивает)
#   5 — id_prev_contract NULL, операция OP_VID=2 (ovClose) -> ни одна ветвь (контрастный код)
#   6 — id_prev_contract NULL, без операций                -> ни одна ветвь
# Ожидание по построению: branch A = {2, 4} = 2; branch B = {3, 4} = 2;
# union (OR) = {2, 3, 4} = 3 — не 4, потому что договор 4 не задваивается.
# ---------------------------------------------------------------------------


def _renewal_fixture(con) -> None:
    seed_contract_states(con)
    insert_contract(con, 1, STATE_OPEN, "2026-01-01", "2026-01-30")
    insert_contract(con, 2, STATE_OPEN, "2026-02-01", "2026-03-01", id_prev_contract=1)
    insert_contract(con, 3, STATE_OPEN, "2026-01-05", "2026-02-04")
    insert_contract(con, 4, STATE_OPEN, "2026-02-10", "2026-03-12", id_prev_contract=2)
    insert_contract(con, 5, STATE_OPEN, "2026-01-01", "2026-01-30")
    insert_contract(con, 6, STATE_OPEN, "2026-01-01", "2026-01-30")
    insert_operation(con, op_id=101, deposit_id=3, op_vid=0, op_date="2026-02-01")
    insert_operation(con, op_id=102, deposit_id=4, op_vid=0, op_date="2026-02-15")
    insert_operation(con, op_id=103, deposit_id=4, op_vid=0, op_date="2026-03-05")
    insert_operation(con, op_id=104, deposit_id=5, op_vid=2, op_date="2026-02-01")


@check("шаг 2: ветвь «Переоткрытие» (id_prev_contract IS NOT NULL) — счёт 2 из 6, {2,4}")
def _t2_branch_reopen():
    con = new_connection()
    _renewal_fixture(con)
    apply_canonization_views(con)
    rows = con.execute(
        "SELECT contract_id FROM lombard_ops.v_renewal_reopen ORDER BY contract_id"
    ).fetchall()
    ids = [r[0] for r in rows]
    assert ids == [2, 4], ids


@check("шаг 3: ветвь «Погашение» (OP_VID = 0) — счёт 2 из 6, {3,4}")
def _t3_branch_repayment():
    con = new_connection()
    _renewal_fixture(con)
    apply_canonization_views(con)
    rows = con.execute(
        "SELECT contract_id FROM lombard_ops.v_renewal_repayment ORDER BY contract_id"
    ).fetchall()
    ids = [r[0] for r in rows]
    assert ids == [3, 4], ids


@check("шаг 4: объединение OR — счёт 3 из 6, {2,3,4}, договор 4 не задвоен")
def _t4_branch_union():
    con = new_connection()
    _renewal_fixture(con)
    apply_canonization_views(con)
    rows = con.execute(
        "SELECT contract_id FROM lombard_ops.v_renewal WHERE renewed ORDER BY contract_id"
    ).fetchall()
    ids = [r[0] for r in rows]
    assert ids == [2, 3, 4], ids
    total = con.execute(
        "SELECT COUNT(*) FROM lombard_ops.v_renewal WHERE renewed"
    ).fetchone()[0]
    assert total == 3, total


# ---------------------------------------------------------------------------
# Шаг 5 · дедупликация снапшота — до/после, плюс обратный замер (один снапшот
# не меняет счёт).
# ---------------------------------------------------------------------------


@check("шаг 5: два снапшота одного contract_id -> ровно 1 строка после дедупликации")
def _t5_dedup_two_snapshots():
    con = new_connection()
    seed_contract_states(con)
    insert_contract(con, 1, STATE_OPEN, "2026-01-01", "2026-01-30",
                     loaded_at="2026-08-01 00:00:00", source_blob="blob-day1")
    insert_contract(con, 1, STATE_OPEN, "2026-01-01", "2026-01-30",
                     loaded_at="2026-08-02 00:00:00", source_blob="blob-day2")
    before = con.execute("SELECT COUNT(*) FROM lombard_ops.raw_contracts").fetchone()[0]
    apply_canonization_views(con)
    after = con.execute("SELECT COUNT(*) FROM lombard_ops.v_raw_contracts_dedup").fetchone()[0]
    kept_blob = con.execute(
        "SELECT source_blob FROM lombard_ops.v_raw_contracts_dedup WHERE contract_id = 1"
    ).fetchone()[0]
    assert before == 2, before
    assert after == 1, after
    assert kept_blob == "blob-day2", kept_blob  # последний по loaded_at


@check("шаг 5 обратный замер: один снапшот -> счёт не меняется дедупликацией")
def _t5_dedup_single_snapshot_unchanged():
    con = new_connection()
    seed_contract_states(con)
    insert_contract(con, 1, STATE_OPEN, "2026-01-01", "2026-01-30")
    insert_contract(con, 2, STATE_OPEN, "2026-02-01", "2026-02-28")
    before = con.execute("SELECT COUNT(*) FROM lombard_ops.raw_contracts").fetchone()[0]
    apply_canonization_views(con)
    after = con.execute("SELECT COUNT(*) FROM lombard_ops.v_raw_contracts_dedup").fetchone()[0]
    assert before == after == 2, (before, after)


# ---------------------------------------------------------------------------
# Шаг 6 · canonical view — client_name/vehicle_* NULL явно, только активные
# договоры (contract_state = OPEN).
# ---------------------------------------------------------------------------


@check("шаг 6: canonical view — client_name и vehicle_* NULL явно, закрытый договор исключён")
def _t6_canonical_view_nulls_and_active_filter():
    con = new_connection()
    seed_contract_states(con)
    insert_contract(con, 1, STATE_OPEN, "2026-07-01", "2026-07-30")
    insert_contract(con, 2, STATE_CLOSED, "2026-06-01", "2026-06-30")
    apply_canonization_views(con)
    rows = con.execute(
        "SELECT contract_id, client_name, vehicle_id, vehicle_make, vehicle_model, vehicle_year "
        "FROM lombard_ops.v_canonization ORDER BY contract_id"
    ).fetchall()
    assert len(rows) == 1, rows  # только договор 1 (OPEN); договор 2 (CLOSED) исключён
    contract_id, client_name, vehicle_id, vehicle_make, vehicle_model, vehicle_year = rows[0]
    assert contract_id == 1
    assert client_name is None
    assert vehicle_id is None
    assert vehicle_make is None
    assert vehicle_model is None
    assert vehicle_year is None


@check("шаг 6: canonical view — issue_date/due_date/renewed/renewed_date по фикстуре")
def _t6_canonical_view_fields():
    con = new_connection()
    seed_contract_states(con)
    insert_contract(con, 1, STATE_OPEN, "2026-07-01", "2026-07-30", id_prev_contract=99)
    apply_canonization_views(con)
    row = con.execute(
        "SELECT issue_date, due_date, offset_days, status_raw, renewed, renewed_date, status "
        "FROM lombard_ops.v_canonization WHERE contract_id = 1"
    ).fetchone()
    issue_date, due_date, offset_days, status_raw, renewed, renewed_date, status = row
    assert issue_date == datetime.date(2026, 7, 1)
    assert due_date == datetime.date(2026, 7, 30)
    assert status_raw == "OPEN"
    assert renewed is True
    assert renewed_date == datetime.date(2026, 7, 1)  # ветвь «Переоткрытие» -> own issue_date
    # offset_days и status считаются от CURRENT_DATE() (дата прогона) — сверяются с той же
    # формулой compute_status(), не с константой (03 §1, ADR-070).
    today = datetime.date.today()
    expected_offset = (today - due_date).days
    expected_status, _ = compute_status(due_date, today)
    assert offset_days == expected_offset, (offset_days, expected_offset)
    assert status == expected_status, (status, expected_status)


# ---------------------------------------------------------------------------
# Шаг 7/8 · формула статуса 03 §1 — единственная реализация + таблица
# эквивалентности SQL vs compute_status() на смещениях -10..+70 включительно.
# ---------------------------------------------------------------------------

EQUIVALENCE_ROWS: list[tuple[int, str, str]] = []


@check("шаг 7-8: таблица эквивалентности статуса -10..+70, SQL vs compute_status()")
def _t8_status_equivalence_table():
    con = new_connection()
    apply_canonization_views(con)
    mismatches = []
    for offset in range(-10, 71):
        due_date = ANCHOR_DUE_DATE
        today = due_date + datetime.timedelta(days=offset)
        sql_offset, sql_status = con.execute(
            "SELECT lombard_ops.offset_days(?, ?), "
            "lombard_ops.status_for_offset(lombard_ops.offset_days(?, ?))",
            [today, due_date, today, due_date],
        ).fetchone()
        py_status, _addressees = compute_status(due_date, today)
        EQUIVALENCE_ROWS.append((offset, sql_status, py_status))
        assert sql_offset == offset, (offset, sql_offset)
        if sql_status != py_status:
            mismatches.append((offset, sql_status, py_status))
    assert not mismatches, f"расхождение SQL vs Python на смещениях: {mismatches}"


# ---------------------------------------------------------------------------
# Шаг 9 · сплошной поиск: ни одного обращения к BigQuery/Firebird в коде
# этой задачи — печать совпадений (пусто) плюс обратный запрос на заведомо
# присутствующей конструкции.
# ---------------------------------------------------------------------------

TASK_FILES = [
    REPO_ROOT / "sql" / "canonization.sql",
    REPO_ROOT / "connector" / "canonize" / "duckdb_runtime.py",
    REPO_ROOT / "connector" / "canonize" / "fixtures.py",
    REPO_ROOT / "connector" / "canonize" / "test_canonization.py",
]

FORBIDDEN_PATTERNS = [
    r"\bbq\.",
    r"google\.cloud\.bigquery",
    r"bigquery\.Client",
    r"\bfdb\b",
    r"\bisql\b",
    r"fire" + r"bird",  # склеено намеренно: иначе строка совпадает САМА С СОБОЙ
    # при сплошном поиске по этому же файлу (шаг 9 сканирует и себя), а это не
    # обращение к базе клиента, а определение шаблона поиска. Разбор — не
    # умолчание: полное имя engine из терминов брифа T-1-2a («Firebird/`fdb`/
    # `isql`») собирается конкатенацией ТОЛЬКО в этом списке, ниоткуда больше
    # не используется и семантику поиска не меняет — `re.search` получает ту
    # же строку `"firebird"`, что и раньше.
]


def _strip_noncode(text: str, is_sql: bool) -> str:
    """Комментарии, докстринги и метки `@check("...")` — не код: реальное
    обращение к BigQuery/Firebird было бы исполняемой строкой (импорт, вызов
    клиента), не текстом объяснения или именем проверки. Убирает `-- ...`
    (SQL) или `# ...` (Python) построчно; для Python — ВСЕ тройные строки
    (докстринги модуля/функций) и строки-декораторы `@check(...)` (это имя
    теста, а не действие)."""
    if is_sql:
        return "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    text = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("@check("):
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines)


@check("шаг 9: сплошной поиск BigQuery/Firebird в коде задачи — 0 совпадений, инструмент исправен")
def _t9_no_cloud_no_client_db_access():
    matches = []
    for path in TASK_FILES:
        raw_text = path.read_text(encoding="utf-8")
        code_text = _strip_noncode(raw_text, is_sql=path.suffix == ".sql")
        for lineno, line in enumerate(code_text.splitlines(), start=1):
            for pattern in FORBIDDEN_PATTERNS:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    matches.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    print("    совпадения запрещённых конструкций в КОДЕ (комментарии/докстринг исключены, ожидается пусто):")
    for m in matches:
        print(f"      {m}")
    if not matches:
        print("      (пусто)")
    assert not matches, matches

    # обратный запрос: заведомо присутствующая конструкция, доказывает исправность поиска
    control_matches = []
    for path in TASK_FILES:
        text = path.read_text(encoding="utf-8")
        if re.search(r"DATE_DIFF", text):
            control_matches.append(str(path.relative_to(REPO_ROOT)))
    print(f"    обратный контроль ('DATE_DIFF' обязан найтись): {control_matches}")
    assert control_matches, "обратный запрос дал 0 совпадений — инструмент поиска неисправен"


# ---------------------------------------------------------------------------
# Шаг 10 · сплошной поиск по репозиторию: ни один потребитель не читает
# loans_raw напрямую (кроме этой задачи и T-1-2b).
# ---------------------------------------------------------------------------


@check("шаг 10: сплошной поиск потребителей loans_raw в коде репозитория (не в .md) — решение по каждому")
def _t10_no_direct_loans_raw_readers():
    code_globs = ["**/*.py", "**/*.sql"]
    hits: list[str] = []
    for pattern in code_globs:
        for path in REPO_ROOT.glob(pattern):
            if "reference" in path.parts:
                continue
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            code_text = _strip_noncode(raw_text, is_sql=path.suffix == ".sql")
            for lineno, line in enumerate(code_text.splitlines(), start=1):
                if "loans_raw" in line:
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    print(f"    совпадения 'loans_raw' в *.py/*.sql (не reference/): {len(hits)}")
    for h in hits:
        print(f"      {h}")
    # Решение по каждому совпадению — механическое, не выдумка: строка либо
    # ЗАПИСЬ (не относится к правилу «не читает»), либо принадлежит контракту
    # схемы (DDL/тест схемы этой же колонки), либо явно этой задаче/T-1-2b.
    read_violations = []
    for h in hits:
        path_part = h.split(":", 1)[0]
        if path_part == "sql/ddl/lombard_ops.sql":
            continue  # DDL самой таблицы — не чтение
        if path_part.startswith("connector/canonize/"):
            continue  # этот же файл сплошного поиска — цитирует имя таблицы, не читает её
        if path_part == "functions/cf_daily/bq_loader.py":
            continue  # ЗАПИСЬ в loans_raw (T-1-0), не чтение — построчно: INSERT/маппинг, не SELECT
        if path_part == "functions/cf_daily/test_bq_loader.py":
            continue  # тест ЗАПИСИ bq_loader, не чтения
        read_violations.append(h)
    assert not read_violations, read_violations


def _print_equivalence_table() -> None:
    print("\n    таблица эквивалентности статуса 03 §1 (SQL vs compute_status()), offset -10..+70:")
    print("    offset | SQL status              | Python status")
    for offset, sql_status, py_status in EQUIVALENCE_ROWS:
        mark = "OK" if sql_status == py_status else "MISMATCH"
        print(f"    {offset:>6} | {sql_status:<24} | {py_status:<24} {mark}")


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
    if EQUIVALENCE_ROWS:
        _print_equivalence_table()
    print(f"\nвсего проверок: {len(_checks)}; провалено {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
