#!/usr/bin/env python3
"""tools/T-2-4_build_seed.py — генератор стартового сида справочника ликвидности `vehicle_catalog`.

Строит базовые строки из дефолтов `03_BUSINESS_SPEC.md §3` (синтетическая скупочная цена,
`price_source: "synthetic"`), затем — если владелец положил `data_inbox/vehicle_catalog.csv` —
накладывает поверх строки из `tools/catalog_import.py` (`price_source: "client"`) по совпадению
`make`+`model`: заменяет синтетическую строку либо добавляет новую, если марки не было в дефолтах.

**Дословный перечень дефолтов `03 §3`** (не досочинять марки сверх названных):
  «Camry 70 🟢 LTV 75%; Prado/RX 🟢 70%; Mercedes E 🟡 55%; Land Rover Discovery 🟡 50%;
   Range Rover / AMG / спорткары — 🔴.»

**Разбор группы на строки — решение исполнителя, названо явно, не спрятано.** Схема
`vehicle_catalog` требует `make`+`model` раздельно (`02 §2`), а текст `03 §3` даёт компактные
группы через «/». Разбор:
  - «Camry 70» → make=Toyota (общеизвестная привязка модели, не изобретённое значение), model=Camry 70
  - «Prado/RX» → ДВЕ строки: Toyota Prado и Lexus RX, обе 🟢 70% — общеизвестные модели этих марок
  - «Mercedes E» → make=Mercedes-Benz, model=E
  - «Land Rover Discovery» → make и model уже раздельны в тексте
  - «Range Rover / AMG / спорткары» → ОДНА конкретная строка Land Rover Range Rover (🔴, без цены).
    «AMG» и «спорткары» НЕ заведены отдельными строками: «AMG» не есть марка/модель сама по себе
    (суббренд Mercedes), «спорткары» — родовое слово, а не конкретный объект каталога; заведение
    строки под них было бы выдумыванием объекта (`05 §I`, третий класс гэпа). Это называется здесь
    явно, а не тихо опускается — то же самое печатается шагом 5 в лог сверки.

Для класса 🔴 `buyout_price` не заполняется (стоп-класс без цены — не дефект, тот же инвариант,
что в `catalog_import.py`). Для 🟢/🟡 `buyout_price` — синтетическое ПРАВДОПОДОБНОЕ, но МНИМОЕ
число (`ADR-064`: «до боевого наполнения ставим моки»), задокументированное здесь как заведомая
выдумка, а не рыночный факт.

Результат — `data_inbox/vehicle_catalog_seed.json`, newline-delimited JSON (один объект на строку,
формат `bq load` без autodetect), шесть полей контракта `02 §2` плюс `price_source`, `updated_at`.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_CSV = os.path.join(REPO_ROOT, "data_inbox", "vehicle_catalog.csv")
CLIENT_SEED_TMP = os.path.join(REPO_ROOT, "data_inbox", "vehicle_catalog_seed.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data_inbox", "vehicle_catalog_seed.json")
CATALOG_IMPORT = os.path.join(REPO_ROOT, "tools", "catalog_import.py")

NOW = datetime.now(timezone.utc).isoformat()

# Синтетические скупочные цены — МНИМЫЕ числа, документированные как моки (ADR-064).
# Ничего из этого не есть рыночный факт; используются только до боевого наполнения.
BASE_ROWS = [
    {"make": "Toyota", "model": "Camry 70", "liquidity_class": "green",
     "ltv_max": 0.75, "buyout_price": 18000.0, "comment": "дефолт ТЗ 03 §3 (мок-цена)"},
    {"make": "Toyota", "model": "Prado", "liquidity_class": "green",
     "ltv_max": 0.70, "buyout_price": 22000.0, "comment": "дефолт ТЗ 03 §3, группа «Prado/RX» (мок-цена)"},
    {"make": "Lexus", "model": "RX", "liquidity_class": "green",
     "ltv_max": 0.70, "buyout_price": 24000.0, "comment": "дефолт ТЗ 03 §3, группа «Prado/RX» (мок-цена)"},
    {"make": "Mercedes-Benz", "model": "E", "liquidity_class": "yellow",
     "ltv_max": 0.55, "buyout_price": 16000.0, "comment": "дефолт ТЗ 03 §3 (мок-цена)"},
    {"make": "Land Rover", "model": "Discovery", "liquidity_class": "yellow",
     "ltv_max": 0.50, "buyout_price": 15000.0, "comment": "дефолт ТЗ 03 §3, восстановлена T-0-21 (мок-цена)"},
    {"make": "Land Rover", "model": "Range Rover", "liquidity_class": "red",
     "ltv_max": None, "buyout_price": None,
     "comment": "дефолт ТЗ 03 §3, группа «Range Rover/AMG/спорткары»; стоп-класс без цены"},
]


def build_base():
    rows = []
    for r in BASE_ROWS:
        rows.append({
            "make": r["make"],
            "model": r["model"],
            "liquidity_class": r["liquidity_class"],
            "ltv_max": r["ltv_max"],
            "buyout_price": r["buyout_price"],
            "comment": r["comment"],
            "price_source": "synthetic",
            "updated_at": NOW,
        })
    return rows


def load_client_rows():
    """Вызывает catalog_import.py как подпроцесс, читает произведённый им сид."""
    result = subprocess.run(
        [sys.executable, CATALOG_IMPORT, "--input", CLIENT_CSV, "--output", CLIENT_SEED_TMP],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    print("--- catalog_import.py (вложенный прогон) ---")
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print("catalog_import.py вернул ненулевой код (%d) — клиентские строки не накладываются." % result.returncode)
        return []
    with open(CLIENT_SEED_TMP, encoding="utf-8") as fh:
        raw_rows = json.load(fh)
    client_rows = []
    for r in raw_rows:
        client_rows.append({
            "make": r["make"],
            "model": r["model"],
            "liquidity_class": r["liquidity_class"],
            "ltv_max": r["ltv_max"],
            "buyout_price": r["buyout_price"],
            "comment": r.get("comment"),
            "price_source": "client",
            "updated_at": NOW,
        })
    return client_rows


def overlay(base_rows, client_rows):
    merged = list(base_rows)
    for crow in client_rows:
        key = (crow["make"].strip().lower(), crow["model"].strip().lower())
        replaced = False
        for i, brow in enumerate(merged):
            if (brow["make"].strip().lower(), brow["model"].strip().lower()) == key:
                merged[i] = crow
                replaced = True
                break
        if not replaced:
            merged.append(crow)
    return merged


def main():
    base_rows = build_base()

    if os.path.exists(CLIENT_CSV):
        client_rows = load_client_rows()
    else:
        print("data_inbox/vehicle_catalog.csv не найден, все марки останутся synthetic")
        client_rows = []

    seed = overlay(base_rows, client_rows)

    # NDJSON — один объект на строку, формат bq load без autodetect.
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        for row in seed:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")

    # --- Печать шага 5: счётчики, распределение, сверка с 03 §3 ---
    print()
    print("=== T-2-4_build_seed.py — итог ===")
    print("строк всего: %d" % len(seed))

    dist_class = {}
    for r in seed:
        dist_class[r["liquidity_class"]] = dist_class.get(r["liquidity_class"], 0) + 1
    print("распределение по liquidity_class: " + ", ".join("%s=%d" % kv for kv in sorted(dist_class.items())))

    dist_source = {}
    for r in seed:
        dist_source[r["price_source"]] = dist_source.get(r["price_source"], 0) + 1
    print("распределение по price_source: " + ", ".join("%s=%d" % kv for kv in sorted(dist_source.items())))

    print()
    print("марка + модель + класс + LTV макс (без buyout_price для строк client — только счётчик):")
    for r in seed:
        price_note = "buyout_price=[СКРЫТО, price_source=client]" if r["price_source"] == "client" else \
            ("buyout_price=%s" % r["buyout_price"] if r["buyout_price"] is not None else "buyout_price=—")
        print("  %-14s %-14s %-6s LTV=%s  %s  price_source=%s" % (
            r["make"], r["model"], r["liquidity_class"],
            (str(r["ltv_max"]) if r["ltv_max"] is not None else "—"),
            price_note, r["price_source"],
        ))

    print()
    print("=== Сверка с дословным перечнем 03 §3 (обе стороны) ===")
    print("03 §3: «Camry 70 🟢 LTV 75%; Prado/RX 🟢 70%; Mercedes E 🟡 55%; "
          "Land Rover Discovery 🟡 50%; Range Rover / AMG / спорткары — 🔴.»")
    print("сгенерировано (make/model/class/ltv):")
    for r in seed:
        if r["price_source"] != "synthetic":
            continue
        print("  %s %s — %s %s" % (r["make"], r["model"], r["liquidity_class"], r["ltv_max"]))
    print("«AMG» и «спорткары» из группы 03 §3 НЕ заведены отдельными строками (не конкретный "
          "make/model, см. docstring скрипта) — названо явно, не пропущено молча.")

    print()
    print("сид записан: %s (%d строк, NDJSON)" % (OUTPUT_PATH, len(seed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
