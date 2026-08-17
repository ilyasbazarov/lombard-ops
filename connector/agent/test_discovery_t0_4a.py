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

import sys

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

    print(f"\nитого провалено: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
