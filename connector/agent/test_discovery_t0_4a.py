"""
connector/agent/test_discovery_t0_4a.py — T-0-4a, шаг 2 (класс A, локально, ОФФЛАЙН)

Прогоняет КАЖДЫЙ запрос модуля `discovery_t0_4a.py` через `validate_query` без
подключения к базе (та же функция, что использует `access_point` перед отправкой
на сервер — правило `ADR-048`: штатный механизм разбора, не второе самодельное
сравнение строк). База клиента этим шагом не трогается вовсе.

Приёмка шага 2 брифа: число проверенных запросов равно числу запросов модуля
(печатается ОБОИМИ числами), провалов ноль, отрицательный случай отбит.

Запуск: `python3 -m connector.agent.test_discovery_t0_4a` из корня репозитория.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from connector.agent import discovery_t0_4a as disc
from connector.agent.access_point import validate_query


def _all_module_queries() -> list[disc.NamedQuery]:
    """Все запросы модуля: STATIC_QUERIES целиком плюс запросы шагов 7-8,
    построенные с ПРИМЕРНЫМ (не боевым) списком кодов OP_VID — офлайн-тест
    проверяет ФОРМУ запроса (проходит белый список), а не значения кодов;
    сами коды в теле шага 7 брифа снимаются с сервера, не отсюда."""
    queries = list(disc.STATIC_QUERIES)
    queries.extend(disc.build_renewal_op_queries([1, 2]))
    return queries


def main() -> int:
    all_queries = _all_module_queries()
    total = len(all_queries)
    failed = 0

    print(f"проверяется запросов модуля: {total}")

    checked = 0
    for nq in all_queries:
        checked += 1
        verdict = validate_query(nq.sql)
        if verdict.ok:
            print(f"[пройдено]  {nq.name}: {verdict.reason}")
        else:
            failed += 1
            print(f"[ПРОВАЛЕНО] {nq.name}: ЗАПРОС ЗАДАЧИ НЕ ПРОШЁЛ БЕЛЫЙ СПИСОК — {verdict.reason}")

    print(f"\nзапросов модуля проверено: {checked}; запросов в модуле: {total}; провалено: {failed}")
    if checked != total:
        print("[ПРОВАЛЕНО] число проверенных запросов не совпало с числом запросов модуля")
        failed += 1

    # Отрицательный случай (ADR-033, «проба обязана различать исходы»): заведомо
    # запрещённый оператор ОБЯЗАН быть отбит — иначе позитивный результат выше
    # ничего не доказывает (белый список мог бы пропускать всё подряд).
    forbidden = "UPDATE CONTRACTS SET CONTRACT_STATE = 0 WHERE 1 = 0"
    verdict = validate_query(forbidden)
    if verdict.ok:
        failed += 1
        print(f"[ПРОВАЛЕНО] отрицательный случай: запрещённый оператор ПРОШЁЛ валидацию — {verdict.reason}")
    else:
        print(f"[пройдено]  отрицательный случай отбит: {verdict.reason}")

    # Положительный контроль для отрицательного случая (ADR-033): один из
    # РЕАЛЬНЫХ запросов задачи обязан наблюдаемо ОТЛИЧАТЬСЯ от запрещённого —
    # иначе «отбит» и «прошёл» неразличимы и проверка не доказывает ничего.
    control = validate_query(disc.ENGINE_VERSION.sql)
    if not control.ok:
        failed += 1
        print(f"[ПРОВАЛЕНО] положительный контроль (engine_version) неожиданно отбит: {control.reason}")
    elif control.ok == verdict.ok:
        failed += 1
        print("[ПРОВАЛЕНО] положительный контроль и отрицательный случай дали ОДИНАКОВЫЙ вердикт")
    else:
        print("[пройдено]  положительный контроль (engine_version) отличим от отрицательного случая")

    # build_renewal_op_queries с пустым списком обязан отказать CONTEXT GAP,
    # а не построить запрос с молчаливо пустым IN () (тихая подстановка нуля).
    try:
        disc.build_renewal_op_queries([])
        failed += 1
        print("[ПРОВАЛЕНО] build_renewal_op_queries([]) обязан кинуть DiscoveryConfigError, а прошёл")
    except disc.DiscoveryConfigError as exc:
        print(f"[пройдено]  build_renewal_op_queries([]) отбит явным CONTEXT GAP: {exc}")

    # CLI (шаг 3+): _resolve_queries обязан различать известное/неизвестное имя
    # запроса ДО открытия соединения — проверяется офлайн, без connection вовсе.
    resolved = disc._resolve_queries(["engine_version", "row_count_control"], ())
    if [q.name for q in resolved] == ["engine_version", "row_count_control"]:
        print("[пройдено]  _resolve_queries: известные имена шага 4 резолвятся в те же запросы")
    else:
        failed += 1
        print(f"[ПРОВАЛЕНО] _resolve_queries вернул не то: {[q.name for q in resolved]!r}")

    try:
        disc._resolve_queries(["not_a_real_query_name"], ())
        failed += 1
        print("[ПРОВАЛЕНО] _resolve_queries с неизвестным именем обязан кинуть DiscoveryConfigError, а прошёл")
    except disc.DiscoveryConfigError as exc:
        print(f"[пройдено]  _resolve_queries отбивает неизвестное имя явным CONTEXT GAP: {exc}")

    resolved_dynamic = disc._resolve_queries(["repayment_active_with_renewal_op"], (1, 2))
    if [q.name for q in resolved_dynamic] == ["repayment_active_with_renewal_op"]:
        print("[пройдено]  _resolve_queries: динамическое имя шага 7 резолвится при переданных renewal_op_vids")
    else:
        failed += 1
        print(f"[ПРОВАЛЕНО] _resolve_queries (динамика) вернул не то: {resolved_dynamic!r}")

    # _read_queries_spec (2026-08-18: control-файл вместо schtasks /change на
    # каждый шаг) — офлайн, файловая система только локальная, база не трогается.
    ns_explicit = argparse.Namespace(queries="engine_version,row_count_control", queries_file=None)
    got = disc._read_queries_spec(ns_explicit)
    if got == "engine_version,row_count_control":
        print("[пройдено]  _read_queries_spec: явный --queries побеждает файл (файл даже не читается)")
    else:
        failed += 1
        print(f"[ПРОВАЛЕНО] _read_queries_spec (явный --queries) вернул не то: {got!r}")

    with tempfile.TemporaryDirectory() as tmp:
        control_file = Path(tmp) / "next_queries.txt"
        control_file.write_text("operations_structure,operation_type_counts\n", encoding="utf-8")
        ns_file = argparse.Namespace(queries=None, queries_file=str(control_file))
        got = disc._read_queries_spec(ns_file)
        if got == "operations_structure,operation_type_counts":
            print("[пройдено]  _read_queries_spec: без --queries читает control-файл")
        else:
            failed += 1
            print(f"[ПРОВАЛЕНО] _read_queries_spec (файл) вернул не то: {got!r}")

        missing_file = Path(tmp) / "does_not_exist.txt"
        ns_missing = argparse.Namespace(queries=None, queries_file=str(missing_file))
        try:
            disc._read_queries_spec(ns_missing)
            failed += 1
            print("[ПРОВАЛЕНО] _read_queries_spec с несуществующим файлом обязан кинуть DiscoveryConfigError, а прошёл")
        except disc.DiscoveryConfigError as exc:
            print(f"[пройдено]  _read_queries_spec отбивает отсутствующий control-файл явным CONTEXT GAP: {exc}")

        empty_file = Path(tmp) / "empty.txt"
        empty_file.write_text("   \n", encoding="utf-8")
        ns_empty = argparse.Namespace(queries=None, queries_file=str(empty_file))
        try:
            disc._read_queries_spec(ns_empty)
            failed += 1
            print("[ПРОВАЛЕНО] _read_queries_spec с пустым control-файлом обязан кинуть DiscoveryConfigError, а прошёл")
        except disc.DiscoveryConfigError as exc:
            print(f"[пройдено]  _read_queries_spec отбивает пустой control-файл явным CONTEXT GAP: {exc}")

        ns_empty_string = argparse.Namespace(queries="", queries_file=str(control_file))
        got = disc._read_queries_spec(ns_empty_string)
        if got == "operations_structure,operation_type_counts":
            print("[пройдено]  _read_queries_spec: пустая строка --queries (falsy) тоже уходит к файлу, не к пустому запуску")
        else:
            failed += 1
            print(f"[ПРОВАЛЕНО] _read_queries_spec (пустой --queries) вернул не то: {got!r}")

    # _read_renewal_op_vids_spec — тот же приём, но НЕОБЯЗАТЕЛЬНЫЙ: отсутствие
    # файла НЕ CONTEXT GAP (в отличие от --queries), просто пустая строка.
    ns_renewal_explicit = argparse.Namespace(renewal_op_vids="0,4", renewal_op_vids_file=None)
    got = disc._read_renewal_op_vids_spec(ns_renewal_explicit)
    if got == "0,4":
        print("[пройдено]  _read_renewal_op_vids_spec: явный --renewal-op-vids побеждает файл")
    else:
        failed += 1
        print(f"[ПРОВАЛЕНО] _read_renewal_op_vids_spec (явный) вернул не то: {got!r}")

    with tempfile.TemporaryDirectory() as tmp:
        missing_renewal_file = Path(tmp) / "renewal_op_vids.txt"
        ns_renewal_missing = argparse.Namespace(renewal_op_vids="", renewal_op_vids_file=str(missing_renewal_file))
        got = disc._read_renewal_op_vids_spec(ns_renewal_missing)
        if got == "":
            print("[пройдено]  _read_renewal_op_vids_spec: отсутствующий файл — пустая строка, НЕ CONTEXT GAP (необязательный вход)")
        else:
            failed += 1
            print(f"[ПРОВАЛЕНО] _read_renewal_op_vids_spec (файла нет) вернул не то: {got!r}")

        renewal_file = Path(tmp) / "renewal_op_vids_present.txt"
        renewal_file.write_text("0\n", encoding="utf-8")
        ns_renewal_file = argparse.Namespace(renewal_op_vids="", renewal_op_vids_file=str(renewal_file))
        got = disc._read_renewal_op_vids_spec(ns_renewal_file)
        if got == "0":
            print("[пройдено]  _read_renewal_op_vids_spec: без --renewal-op-vids читает control-файл")
        else:
            failed += 1
            print(f"[ПРОВАЛЕНО] _read_renewal_op_vids_spec (файл) вернул не то: {got!r}")

    print(f"\nитого провалено: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
