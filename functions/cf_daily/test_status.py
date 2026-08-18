"""
functions/cf_daily/test_status.py — T-1-0, шаг 2

По одной проверке на каждую строку таблицы порогов `03_BUSINESS_SPEC.md §1`
плюс граничные значения (−7 включительно, −6 включительно). Запуск:
`cd functions/cf_daily && python3 test_status.py` — корень импорта совпадает
с контейнером (`/workspace`).
"""

from __future__ import annotations

import datetime
import sys
import traceback
from typing import Any

from status import (
    ASSESSOR,
    MANAGER,
    OWNER,
    STATUS_GREEN,
    STATUS_ORANGE_OVERDUE,
    STATUS_ORANGE_PREMARKETING,
    STATUS_RED_REALIZATION,
    STATUS_YELLOW,
    compute_status,
)

DUE_DATE = datetime.date(2026, 7, 30)

_checks: list[tuple[str, Any]] = []


def check(name: str):
    def deco(fn):
        _checks.append((name, fn))
        return fn

    return deco


def _today(offset: int) -> datetime.date:
    return DUE_DATE + datetime.timedelta(days=offset)


@check("строка 1: −7 и раньше -> 🟢 Активный, никто не уведомляется")
def _t_row1():
    label, notify = compute_status(DUE_DATE, _today(-7))
    assert label == STATUS_GREEN
    assert notify == ()


@check("граница −7 включительно (тот же offset, отдельная проверка формы брифа)")
def _t_boundary_minus7():
    label, notify = compute_status(DUE_DATE, _today(-7))
    assert label == STATUS_GREEN
    assert notify == ()


@check("граница −6 включительно -> уже 🟡 Внимание (переход диапазона)")
def _t_boundary_minus6():
    label, notify = compute_status(DUE_DATE, _today(-6))
    assert label == STATUS_YELLOW
    assert notify == (MANAGER,)


@check("строка 2: −6…+1 -> 🟡 Внимание, Бектур (проверка серединой диапазона, +1)")
def _t_row2():
    label, notify = compute_status(DUE_DATE, _today(1))
    assert label == STATUS_YELLOW
    assert notify == (MANAGER,)


@check("строка 3: +2 -> 🟠 Просрочен, Бектур + Иса")
def _t_row3():
    label, notify = compute_status(DUE_DATE, _today(2))
    assert label == STATUS_ORANGE_OVERDUE
    assert notify == (MANAGER, OWNER)


@check("строка 4: +16 -> 🟠 Пре-маркетинг, Эльхан + Иса")
def _t_row4():
    label, notify = compute_status(DUE_DATE, _today(16))
    assert label == STATUS_ORANGE_PREMARKETING
    assert notify == (ASSESSOR, OWNER)


@check("строка 5: +32 -> 🔴 Реализация, Эльхан + Иса")
def _t_row5():
    label, notify = compute_status(DUE_DATE, _today(32))
    assert label == STATUS_RED_REALIZATION
    assert notify == (ASSESSOR, OWNER)


@check("строка 6а: +39 -> 🔴, адресат сужается до Исы (точечная сводка)")
def _t_row6a():
    label, notify = compute_status(DUE_DATE, _today(39))
    assert label == STATUS_RED_REALIZATION
    assert notify == (OWNER,)


@check("строка 6б: +46 -> 🔴, адресат Иса")
def _t_row6b():
    label, notify = compute_status(DUE_DATE, _today(46))
    assert label == STATUS_RED_REALIZATION
    assert notify == (OWNER,)


@check("строка 6в: +62 -> 🔴, адресат Иса")
def _t_row6c():
    label, notify = compute_status(DUE_DATE, _today(62))
    assert label == STATUS_RED_REALIZATION
    assert notify == (OWNER,)


@check("контраст: +40 (день ПОСЛЕ точечного +39) -> 🔴, адресат снова Эльхан + Иса")
def _t_contrast_after_milestone():
    label, notify = compute_status(DUE_DATE, _today(40))
    assert label == STATUS_RED_REALIZATION
    assert notify == (ASSESSOR, OWNER)


def main() -> int:
    failed = 0
    for name, fn in _checks:
        try:
            fn()
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"[ПРОВАЛЕНО] {name}")
            traceback.print_exc()
        else:
            print(f"[пройдено]  {name}")
    print(f"\nвсего проверок: {len(_checks)}; провалено {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
