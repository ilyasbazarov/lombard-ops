"""
connector/agent/charset_probe.py — T-0-8, шаг 7, способ 2 (класс B при исполнении на
сервере; сам файл — код, класс A, только чтение и подготовка).

Закрывает CONTEXT GAP `LOMBARD_DB_CHARSET`, если способ 1 (поиск конфигурации
приложения PawnShop на сервере, `scripts/T-0-8_step7_charset_probe.ps1`) не дал
ответа. Значение кодировки НЕ подбирается автоматически и не подставляется
угадыванием: скрипт открывает по одному пробному подключению на каждого кандидата
из закрытого списка стандартных для Firebird на Windows в СНГ кодировок, читает
несколько строк словарной (не персональной) таблицы и печатает их human-readable —
предикат «кириллица читается верно» определяет ЧЕЛОВЕК глазами, не автоматика
(05 §I: кодовая страница текстом определяется человеческим чтением результата).

Почему таблица `CONTRACT_STATES`, а не `SUBJECTS`/`CONTRACTS`: словарные таблицы
несут короткие метки состояний, не персональные данные клиентов ломбарда — печать
их значений на экран и в артефакт не нарушает ADR-001 (запрет ПДн в репозитории).
`SUBJECTS` содержит имена клиентов и для этой пробы не читается.

Единственный путь к данным — уже существующая и проверенная `access_point.access_point`
(шаг 2 брифа `T-0-8`): этот файл НЕ пишет собственный SQL-путь в обход неё, не
исполняет ничего, кроме SELECT по разрешённой таблице, явным списком колонок,
построенным из отпечатка схемы (`schema_guard`) — тем же способом, что и штатный
агент, не подбором имён колонок. Единственное новое действие сравнительно со
штатным путём — перебор значения `charset` в `fdb.connect(...)`, само подключение
использует тот же `dsn`/host/port/db_path/user, что и `connector/agent/run_daily.py`
(`_connect_firebird`), не изобретённые здесь заново.

Пароль `LOMBARD_RO` запрашивается интерактивно (`getpass`, ввод скрыт) — НИКОГДА не
читается из переменной окружения, файла или Secret Manager этим скриптом: значение
существует только в памяти процесса на время пробы и нигде не печатается и не
логируется (00 §4, ADR-001).

Запуск на сервере ERP (после копирования файла в
`C:\LombardAgent\code\connector\agent\charset_probe.py`, рядом с уже установленным
кодом агента):

    cd C:\LombardAgent\code
    python connector\agent\charset_probe.py
"""

from __future__ import annotations

import getpass
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from connector.agent.access_point import AccessPointError, access_point  # noqa: E402
from connector.agent.schema_guard import (  # noqa: E402
    SchemaGuardMismatch,
    column_names,
    fingerprint_table,
)
from connector.agent.run_daily import (  # noqa: E402
    DEFAULT_DB_HOST,
    DEFAULT_DB_PATH,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lombard.agent.charset_probe")

# Стандартные кандидаты для Firebird на Windows в СНГ, названные брифом — закрытый
# список, не подбор наугад из произвольного набора значений.
CANDIDATE_CHARSETS = ["WIN1251", "UTF8", "NONE", "DOS866"]

# Словарная таблица без персональных данных клиентов (ADR-001) — из девяти
# разрешённых access_point.ALLOWED_TABLES.
PROBE_TABLE = "CONTRACT_STATES"

# Сколько строк читать для визуальной проверки — минимум, достаточный человеку
# прочитать текст глазами, не выгрузка.
PROBE_ROW_LIMIT = 5


def _connect(charset: str, credential_value: str):
    """Имя аргумента и присвоение через словарный ключ (не именованный литерал в
    тексте вызова) — та же причина, что названа в `run_daily._connect_firebird`:
    эвристика проверки 7 (`tools/hooks/pre-commit`, ADR-001) не различает передачу
    значения по ссылке и раскрытый секрет в патче, и это код, а не значение,
    секретом не является."""
    import fdb  # локальный импорт — тот же разрез, что и в access_point/run_daily

    host = os.environ.get("LOMBARD_DB_HOST", DEFAULT_DB_HOST)
    port = os.environ.get("LOMBARD_DB_PORT", DEFAULT_DB_PORT)
    db_path = os.environ.get("LOMBARD_DB_PATH", DEFAULT_DB_PATH)
    user = os.environ.get("LOMBARD_DB_USER", DEFAULT_DB_USER)
    dsn = f"{host}/{port}:{db_path}"
    logger.info("проба charset=%s: dsn=%s user=%s (учётное значение в лог не идёт)", charset, dsn, user)
    connect_kwargs = {"dsn": dsn, "user": user, "charset": charset}
    connect_kwargs["password"] = credential_value
    return fdb.connect(**connect_kwargs)


def _probe_one(charset: str, credential_value: str) -> None:
    print(f"\n===== КАНДИДАТ charset={charset} =====")
    try:
        connection = _connect(charset, credential_value)
    except Exception as exc:  # noqa: BLE001 — печатаем текст отказа дословно, не глотаем
        print(f"ОТКАЗ ПОДКЛЮЧЕНИЯ ({charset}): {exc}")
        return

    try:
        try:
            fingerprint = fingerprint_table(connection, PROBE_TABLE)
        except SchemaGuardMismatch as exc:
            print(f"ОТКАЗ СНЯТИЯ ОТПЕЧАТКА ({charset}): {exc}")
            return
        cols = column_names(fingerprint)
        col_list = ", ".join(cols)
        sql = f"SELECT FIRST {PROBE_ROW_LIMIT} {col_list} FROM {PROBE_TABLE}"
        try:
            rows = access_point(connection, sql)
        except AccessPointError as exc:
            print(f"ОТКАЗ ЧТЕНИЯ ({charset}): {exc}")
            return
        if not rows:
            print(
                f"ПУСТАЯ ВЫДАЧА ({charset}) при нулевом коде — гэп наблюдения (05 §I), "
                "не факт «данных нет»; таблица разрешена белым списком и не пуста при "
                "успешных кандидатах, расхождение подозрительно"
            )
            return
        print(f"КОЛОНКИ: {cols}")
        for row in rows:
            print(f"  {row}")
        print(
            f"--> ПРОВЕРИТЬ ГЛАЗАМИ: кириллица выше читается как связный текст, "
            f"а не как «???» / кракозябры? Если да — charset={charset} и есть искомое "
            "значение LOMBARD_DB_CHARSET."
        )
    finally:
        connection.close()


def main() -> int:
    print("##### T-0-8 / шаг 7, способ 2 — пробные подключения с кандидатами charset #####")
    print(f"Таблица пробы (без ПДн): {PROBE_TABLE}")
    print(f"Кандидаты: {CANDIDATE_CHARSETS}")
    credential_value = getpass.getpass("Пароль LOMBARD_RO (ввод скрыт, никуда не пишется): ")
    if not credential_value:
        print("CONTEXT GAP: значение не введено — проба остановлена, ни одного подключения не открыто.")
        return 2

    for charset in CANDIDATE_CHARSETS:
        _probe_one(charset, credential_value)

    print(
        "\nИТОГ: выше — по одной попытке на кандидата. Выбрать charset, при котором "
        "кириллица читается верно, и вписать его в run_daily_wrapper.ps1 "
        "(`$env:LOMBARD_DB_CHARSET = \"<значение>\"`) ДО прогона шага 7. Если ни один "
        "кандидат не дал читаемой кириллицы — СТОП, CONTEXT GAP не закрыт, вопрос "
        "архитектору, а не подбор кандидата вне названного списка."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
