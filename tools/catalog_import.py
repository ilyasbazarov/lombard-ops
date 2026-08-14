#!/usr/bin/env python3
"""Импорт справочника ликвидности из выгрузки листа «Справочник» (Google Sheets → CSV).

Механизм приёма файла назван целиком, чтобы ни одна его часть не оставалась на владельце
догадкой (`ADR-060`):

  1. Владелец в Google Sheets: Файл → Скачать → CSV (лист «Справочник»).
  2. Кладёт файл ровно сюда:  data_inbox/vehicle_catalog.csv
     Каталог `data_inbox/` в `.gitignore` целиком, кроме шаблона: скупочные цены — коммерческая
     информация клиента, а репозиторий публичный (`00 §4`).
  3. Дальше работает этот скрипт: проверяет шапку, нормализует значения, печатает счёт и
     распределение, кладёт готовый сид в data_inbox/vehicle_catalog_seed.json.
  4. Заливка сида в BigQuery — отдельный шаг класса B по карточке (`T-2-4`).

Скрипт НИЧЕГО не угадывает: нет файла — печатает CONTEXT GAP с точным путём и ожидаемой шапкой;
не сошлась шапка — печатает ОБЕ стороны; строка не разобрана — называется номером и причиной,
а не отбрасывается молча. Пустая выдача фактом «ошибок нет» не является: итог печатает числа.

Запуск:
    python3 tools/catalog_import.py                      # путь по умолчанию
    python3 tools/catalog_import.py --input <файл>       # другой файл
    python3 tools/catalog_import.py --template           # напечатать шаблон шапки и выйти
"""

import argparse
import csv
import json
import os
import re
import sys

DEFAULT_INPUT = "data_inbox/vehicle_catalog.csv"
DEFAULT_OUTPUT = "data_inbox/vehicle_catalog_seed.json"

# Шапка листа «Справочник» — назначена владельцем 2026-08-13, дословно.
EXPECTED_HEADER = [
    "Марка",
    "Модель",
    "Ликвидность",
    "LTV макс",
    "Скупочная база",
    "Комментарий",
]

# Класс ликвидности: и эмодзи, и слово — лист заполняет человек, а не машина.
LIQUIDITY = {
    "🟢": "green", "зелёный": "green", "зеленый": "green", "green": "green", "высокая": "green",
    "🟡": "yellow", "жёлтый": "yellow", "желтый": "yellow", "yellow": "yellow", "средняя": "yellow",
    "🔴": "red", "красный": "red", "red": "red", "стоп": "red",
}

EMPTY_MARKS = {"", "—", "-", "–", "n/a", "нет", "не берём", "не берем"}


def parse_pct(raw):
    """«75%» / «75» / «0,75» → 0.75. Возвращает (значение, ошибка)."""
    s = str(raw).strip().replace(",", ".").replace("%", "").replace(" ", "")
    if s.lower() in EMPTY_MARKS:
        return None, None
    try:
        v = float(s)
    except ValueError:
        return None, "не число"
    if v > 1.0:
        v = v / 100.0
    if not (0.0 < v <= 1.0):
        return None, "доля вне диапазона (0, 1]"
    return round(v, 4), None


def parse_money(raw):
    """«$18,000» / «18 000» / «18000.50» → 18000.0. Возвращает (значение, ошибка)."""
    s = str(raw).strip()
    if s.lower() in EMPTY_MARKS:
        return None, None
    s = re.sub(r"[^\d,.\-]", "", s)
    # Запятая как разделитель тысяч: «18,000» → 18000; как десятичная: «18000,50» → 18000.50.
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[-1]) != 3:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None, "не число"
    if v < 0:
        return None, "отрицательная сумма"
    return v, None


def parse_liquidity(raw):
    s = str(raw).strip().lower()
    for key, val in LIQUIDITY.items():
        if key.lower() in s:
            return val, None
    return None, "класс ликвидности не распознан"


def context_gap(path):
    print("CONTEXT GAP: файл справочника ликвидности отсутствует и угадыванию не подлежит.")
    print("  ожидался путь : %s" % path)
    print("  как получить  : Google Sheets, лист «Справочник» → Файл → Скачать → CSV")
    print("  ожидаемая шапка (порядок колонок обязателен):")
    print("    " + ",".join(EXPECTED_HEADER))
    print("  скупочные цены — коммерческая информация клиента: каталог data_inbox/ в .gitignore,")
    print("  в публичный репозиторий файл не уходит (00 §4).")
    return 2


def main():
    ap = argparse.ArgumentParser(description="Импорт справочника ликвидности из CSV.")
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--template", action="store_true", help="напечатать шаблон шапки и выйти")
    args = ap.parse_args()

    if args.template:
        print(",".join(EXPECTED_HEADER))
        return 0

    if not os.path.exists(args.input):
        return context_gap(args.input)

    with open(args.input, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))

    if not rows:
        print("ОТКАЗ: файл %s пуст — это не «ноль марок», это нечитаемый вход." % args.input)
        return 2

    header = [c.strip() for c in rows[0]][: len(EXPECTED_HEADER)]
    if header != EXPECTED_HEADER:
        print("ОТКАЗ: шапка не совпала. Обе стороны печатаются целиком:")
        print("  ожидалось: %s" % EXPECTED_HEADER)
        print("  в файле  : %s" % header)
        return 2
    print("шапка совпала: %s" % ",".join(header))

    seed, rejected = [], []
    for idx, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        row = (row + [""] * len(EXPECTED_HEADER))[: len(EXPECTED_HEADER)]
        make, model, liq_raw, ltv_raw, price_raw, comment = [c.strip() for c in row]

        if not make or not model:
            rejected.append((idx, "пустая марка или модель"))
            continue

        liq, err = parse_liquidity(liq_raw)
        if err:
            rejected.append((idx, "%s: «%s»" % (err, liq_raw)))
            continue

        ltv, err = parse_pct(ltv_raw)
        if err:
            rejected.append((idx, "LTV — %s: «%s»" % (err, ltv_raw)))
            continue

        price, err = parse_money(price_raw)
        if err:
            rejected.append((idx, "скупочная база — %s: «%s»" % (err, price_raw)))
            continue

        # Стоп-класс без LTV и цены — это НЕ дефект строки: «не берём» и есть значение.
        if liq != "red" and (ltv is None or price is None):
            rejected.append((idx, "класс %s требует и LTV, и скупочную базу" % liq))
            continue

        seed.append({
            "make": make,
            "model": model,
            "liquidity_class": liq,
            "ltv_max": ltv,
            "buyout_price": price,
            "max_loan_by_catalog": round(ltv * price, 2) if (ltv is not None and price is not None) else None,
            "comment": comment or None,
            "source_row": idx,
        })

    dist = {}
    for r in seed:
        dist[r["liquidity_class"]] = dist.get(r["liquidity_class"], 0) + 1

    print("строк принято : %d" % len(seed))
    print("строк отклонено: %d" % len(rejected))
    for idx, why in rejected:
        print("  строка %d — %s" % (idx, why))
    print("распределение по классам: " + (", ".join("%s=%d" % kv for kv in sorted(dist.items())) or "пусто"))

    if not seed:
        print("ОТКАЗ: ни одна строка не принята — сид не пишется.")
        return 2

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(seed, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("сид записан: %s (%d строк)" % (args.output, len(seed)))
    print("следующий шаг — заливка в BigQuery, класс B по карточке (T-2-4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
