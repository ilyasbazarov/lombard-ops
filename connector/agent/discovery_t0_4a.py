"""
connector/agent/discovery_t0_4a.py — T-0-4a, шаг 1 (класс A, локально)

Модуль замера для брифа `briefs/T-0-4a.md`. Каждый запрос идёт через единственную
точку доступа (`connector.agent.access_point.access_point`) — здесь нет ни одного
`cursor.execute` напрямую и ни одного второго пути к базе PawnShop.

**Подключение** открывается CLI (`cli_main`, ниже) ТЕМ ЖЕ способом, что в
`run_daily.py` — реюзом его приватных функций (`_refresh_jwt`,
`_fetch_db_credential_value`, `_connect_firebird`), а не вторым написанным
заново механизмом; переменные окружения те же (`LOMBARD_DB_HOST/PORT/PATH/USER`,
`LOMBARD_DB_CHARSET`, `PROJECT_ID`, `LOMBARD_AGENT_*`) и Secret Manager для
пароля. Модуль не пишет ничего, кроме лога через `logging`.

**Класс исполнения.** Написание и импорт этого файла — класс A (код без
применения). Реальный запуск CLI ПРОТИВ БОЕВОЙ БАЗЫ — класс B: каждый вызов на
сервере ERP исполняется только после отдельной карточки подтверждения владельца
(шаги 3 и далее брифа `T-0-4a`), и вызов охватывает РОВНО ОДИН шаг брифа
(`--queries` называет его именованные запросы явно) — не «прогнать всё».

**Санитария (`ADR-039`, дословно из брифа).** Каждый запрос ниже — либо агрегат
(счёт, группировка, распределение), либо каталог метаданных (имена/типы колонок,
описания из `RDB$*`), либо ограниченная выборка ДАТ без идентификаторов договора
(пары «старый → новый» из шага 6 отдают только `CONTRACT_DATE` обеих сторон связи,
без `CONTRACT_ID`/`CONTRACT_NUM` — печать порядковым номером выборки делает вызывающий
код, не SQL). Ни один запрос не выбирает номер договора, имя человека или VIN как
значение строки.

**Таблицы** — исключительно из `ALLOWED_TABLES` (`access_point.py`) плюс системные
`RDB$*`; попытка обратиться к таблице вне списка отбивается `validate_query` ДО
отправки на сервер, а не после — это гарантия точки доступа, не этого модуля.

**Два класса запросов.**
  - `STATIC_QUERIES` — фиксированный текст, не зависящий от результата других
    запросов. Полностью проверяется офлайн-тестом (`test_discovery_t0_4a.py`).
  - Запросы шагов 7–8 (ветвь «Погашение» и сводная доля) ЗАВИСЯТ от того, какие
    коды `OPERATIONS.OP_VID` по смыслу означают продление/частичное погашение —
    этот список кодов достаём из описания колонки `OP_VID`, снятого запросом
    `operations_structure` (тем же приёмом, что уже сработал на `CONTRACT_STATE`
    в `T-0-3b`: справочник значений лежит текстом в `RDB$DESCRIPTION`). Значения
    кодов НЕ угадываются здесь — `build_renewal_op_queries()` требует явный
    непустой список `renewal_op_vids`, поданный ПОСЛЕ того, как шаг 5 брифа
    прочитал реальное описание колонки на сервере; вызов с пустым списком кидает
    `DiscoveryConfigError` вместо того, чтобы подставить произвольное число
    (anti-improvisation, `CLAUDE.md`).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

# Тот же приём, что `run_daily.py` (тоже `connector/agent/<файл>.py`, тот же
# уровень вложенности): при запуске ПРЯМО как скрипт по абсолютному пути
# (`python C:\LombardAgent\code\connector\agent\discovery_t0_4a.py`, а не
# `python -m connector.agent.discovery_t0_4a`) интерпретатор кладёт в
# `sys.path[0]` каталог САМОГО файла (`connector/agent/`), а не корень
# репозитория — импорт `connector.agent.access_point` тогда падает
# `ModuleNotFoundError: No module named 'connector'`, потому что пакет
# `connector` с этой точки не виден. Найдено реальным прогоном на сервере
# ERP 2026-08-18 (`t0_4a_discovery_20260818_005757.err.log`, шаг 4 брифа
# T-0-4a): у `run_daily.py` та же схема запуска (обёртка вызывает его тоже
# абсолютным путём), и там это решено ровно этой строкой — тем же способом
# и здесь, а не вторым отдельным механизмом.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from connector.agent.access_point import access_point  # noqa: E402

logger = logging.getLogger("lombard.agent.discovery_t0_4a")

# Порог печати строк на запрос: агрегаты этой задачи (справочники, распределения,
# короткие выборки) по конструкции малы — если запрос вернул больше, это сигнал,
# что запрос не тот агрегат, каким задуман, а не повод печатать тысячи строк.
_MAX_ROWS_PRINTED = 200


class DiscoveryConfigError(Exception):
    """Вход, нужный для построения запроса, не предъявлен — значение не
    подставляется угадыванием (anti-improvisation, CLAUDE.md)."""


@dataclass(frozen=True)
class NamedQuery:
    name: str
    sql: str
    params: tuple = ()
    note: str = ""


# ---------------------------------------------------------------------------
# Шаг 4 брифа — положительные контроли первого прогона (сам access_point на
# каждый вызов уже печатает MON$READ_ONLY положительным фактом — третья
# величина приёмки получается автоматически, отдельного запроса под неё не
# заводится).
# ---------------------------------------------------------------------------

ENGINE_VERSION = NamedQuery(
    name="engine_version",
    sql="SELECT RDB$GET_CONTEXT('SYSTEM', 'ENGINE_VERSION') AS ENGINE_VERSION FROM RDB$DATABASE",
    note="шаг 4: версия движка — контроль 'содержит 2.5'",
)

ROW_COUNT_CONTROL = NamedQuery(
    name="row_count_control",
    sql="SELECT COUNT(*) AS CNT FROM DEPOSIT_TYPES",
    note="шаг 4: счёт строк одной разрешённой (маленькой, справочной) таблицы",
)

# ---------------------------------------------------------------------------
# Шаг 5 брифа — устройство журнала операций.
# ---------------------------------------------------------------------------

OPERATIONS_STRUCTURE = NamedQuery(
    name="operations_structure",
    sql=(
        "SELECT f.RDB$FIELD_NAME AS COLUMN_NAME, "
        "t.RDB$FIELD_TYPE AS FIELD_TYPE, "
        "t.RDB$FIELD_LENGTH AS FIELD_LENGTH, "
        "t.RDB$FIELD_SCALE AS FIELD_SCALE, "
        "f.RDB$DESCRIPTION AS COLUMN_DESCRIPTION "
        "FROM RDB$RELATION_FIELDS f "
        "JOIN RDB$FIELDS t ON t.RDB$FIELD_NAME = f.RDB$FIELD_SOURCE "
        "WHERE f.RDB$RELATION_NAME = ? "
        "ORDER BY f.RDB$FIELD_POSITION"
    ),
    params=("OPERATIONS",),
    note=(
        "шаг 5: состав OPERATIONS — имена, типы, описания на русском из метаданных "
        "(тот же приём, что T-0-3b на CONTRACT_STATE: справочник значений колонки "
        "часто лежит текстом в RDB$DESCRIPTION — здесь ищем то же для OP_VID)"
    ),
)

OPERATION_TYPE_COUNTS = NamedQuery(
    name="operation_type_counts",
    sql="SELECT OP_VID, COUNT(*) AS CNT FROM OPERATIONS GROUP BY OP_VID ORDER BY OP_VID",
    note="шаг 5: справочник типов операций агрегатами — какие есть и сколько записей каждого",
)

# ---------------------------------------------------------------------------
# Шаг 6 брифа — ветвь «Переоткрытие» (ID_PREV_CONTRACT).
# ---------------------------------------------------------------------------

ACTIVE_TOTAL = NamedQuery(
    name="active_total",
    sql=(
        "SELECT COUNT(*) AS ACTIVE_TOTAL "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "WHERE st.CODE = 'OPEN'"
    ),
    note="знаменатель для всех долей 'по активному портфелю' (CODE='OPEN' — снято T-0-3b, Q-7)",
)

REOPEN_ACTIVE_WITH_PREV = NamedQuery(
    name="reopen_active_with_prev",
    sql=(
        "SELECT COUNT(*) AS ACTIVE_WITH_PREV "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "WHERE st.CODE = 'OPEN' AND c.ID_PREV_CONTRACT IS NOT NULL"
    ),
    note="шаг 6: сколько активных договоров имеют непустую связь с предыдущим",
)

# ТРЕТЬЯ правка (2026-08-18): рекурсивный WITH дал `SQLCODE -104 "CTE ...
# has cyclic dependencies"` ДВАЖДЫ подряд с разными формами текста (без и с
# явным списком колонок CTE, без и с `WHERE ch.DEPTH < 500`) — гипотеза
# «форма записи» экспериментально не подтвердилась, вторая попытка её
# вариации без нового основания была бы тем самым угадыванием, которое
# запрещено (anti-improvisation). Задокументированного факта именно про это
# сообщение Firebird 2.5 в репозитории нет (сплошной поиск `grep -rn
# "SQLCODE.*-104\|cyclic dependencies"` — 0 совпадений до этой правки), и
# средства добыть его СНАРУЖИ репозитория (веб-поиск/документация вендора)
# у этой сессии нет — внешний источник тут в любом случае был бы только
# гипотезой, не фактом (`ADR-045`). Причина ошибки движка остаётся
# НЕОБЪЯСНЕННОЙ и не выдаётся за объяснённую.
#
# Вместо третьей вариации синтаксиса — ОБХОД без рекурсивного `WITH` вовсе:
# фиксированное число последовательных `LEFT JOIN CONTRACTS` по
# `ID_PREV_CONTRACT` (глубина 10 = сама строка + 9 уровней предков).
# Обоснование потолка числом, не догадкой: `reopen_active_with_prev`
# (тот же прогон, что и это поле) дал 44 активных договора с непустым
# `ID_PREV_CONTRACT` — небольшое число, глубокие цепочки в портфеле такого
# размера маловероятны, и `OPERATIONS.OP_VID = 3` (`ovReopen`) в шаге 5 не
# встретился НИ РАЗУ, что говорит скорее о редком использовании ветви
# «Переоткрытие», а не о длинных цепочках. **Число НЕ точное, если реальная
# цепочка длиннее 10** — это явно печатается запросом-предупреждением
# `reopen_chain_length_saturated_check` ниже (сколько цепочек «упёрлись» в
# 10-й уровень, всё ещё не найдя корень): `0` — потолок точно достаточен;
# `> 0` — `MAX_CHAIN_LENGTH` есть НИЖНЯЯ оценка, факт называется поимённо,
# а не молчится.
REOPEN_MAX_CHAIN_LENGTH = NamedQuery(
    name="reopen_max_chain_length",
    sql=(
        "SELECT MAX("
        "1"
        " + CASE WHEN l1.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l2.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l3.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l4.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l5.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l6.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l7.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l8.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        " + CASE WHEN l9.CONTRACT_ID IS NOT NULL THEN 1 ELSE 0 END"
        ") AS MAX_CHAIN_LENGTH "
        "FROM CONTRACTS c "
        "LEFT JOIN CONTRACTS l1 ON l1.CONTRACT_ID = c.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l2 ON l2.CONTRACT_ID = l1.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l3 ON l3.CONTRACT_ID = l2.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l4 ON l4.CONTRACT_ID = l3.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l5 ON l5.CONTRACT_ID = l4.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l6 ON l6.CONTRACT_ID = l5.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l7 ON l7.CONTRACT_ID = l6.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l8 ON l8.CONTRACT_ID = l7.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l9 ON l9.CONTRACT_ID = l8.ID_PREV_CONTRACT"
    ),
    note=(
        "шаг 6: максимальная длина цепочки переоткрытий — БЕЗ рекурсивного WITH "
        "(см. комментарий над константой: -104 'has cyclic dependencies' дважды "
        "подряд на разных формах рекурсивного запроса, причина не установлена). "
        "Бескурсивная замена: 9 последовательных LEFT JOIN CONTRACTS по "
        "ID_PREV_CONTRACT, потолок глубины 10 обоснован числом 44 (reopen_active_with_prev) "
        "и нулевым OP_VID=3 в шаге 5, не догадкой. Насыщение потолка проверяется "
        "отдельным запросом reopen_chain_length_saturated_check."
    ),
)

REOPEN_CHAIN_LENGTH_SATURATED_CHECK = NamedQuery(
    name="reopen_chain_length_saturated_check",
    sql=(
        "SELECT COUNT(*) AS SATURATED_AT_10 "
        "FROM CONTRACTS c "
        "LEFT JOIN CONTRACTS l1 ON l1.CONTRACT_ID = c.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l2 ON l2.CONTRACT_ID = l1.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l3 ON l3.CONTRACT_ID = l2.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l4 ON l4.CONTRACT_ID = l3.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l5 ON l5.CONTRACT_ID = l4.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l6 ON l6.CONTRACT_ID = l5.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l7 ON l7.CONTRACT_ID = l6.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l8 ON l8.CONTRACT_ID = l7.ID_PREV_CONTRACT "
        "LEFT JOIN CONTRACTS l9 ON l9.CONTRACT_ID = l8.ID_PREV_CONTRACT "
        "WHERE l9.CONTRACT_ID IS NOT NULL AND l9.ID_PREV_CONTRACT IS NOT NULL"
    ),
    note=(
        "проверка насыщения потолка глубины 10 у reopen_max_chain_length: строка "
        "'дошла' до 10-го уровня И у него самого ещё есть предок — то есть "
        "потолка не хватило, MAX_CHAIN_LENGTH=10 будет НИЖНЕЙ оценкой, не фактом. "
        "0 — потолок 10 точно достаточен для всего портфеля."
    ),
)

REOPEN_CONTRACTS_IN_CHAINS = NamedQuery(
    name="reopen_contracts_in_chains",
    sql=(
        "SELECT COUNT(*) AS IN_CHAIN FROM CONTRACTS c "
        "WHERE c.ID_PREV_CONTRACT IS NOT NULL "
        "OR c.CONTRACT_ID IN (SELECT ID_PREV_CONTRACT FROM CONTRACTS WHERE ID_PREV_CONTRACT IS NOT NULL)"
    ),
    note="шаг 6: сколько договоров портфеля (любого статуса) стоят в цепочках хоть одной стороной",
)

REOPEN_SAMPLE_PAIRS = NamedQuery(
    name="reopen_sample_pairs",
    sql=(
        "SELECT FIRST 20 c.CONTRACT_DATE AS NEW_DATE, p.CONTRACT_DATE AS PREV_DATE "
        "FROM CONTRACTS c "
        "JOIN CONTRACTS p ON p.CONTRACT_ID = c.ID_PREV_CONTRACT "
        "WHERE c.ID_PREV_CONTRACT IS NOT NULL "
        "ORDER BY c.CONTRACT_DATE"
    ),
    note=(
        "шаг 6: пары 'старый -> новый' датами БЕЗ идентификаторов договора — "
        "печать порядковым номером выборки делает вызывающий код (см. print_reopen_pairs)"
    ),
)

# ---------------------------------------------------------------------------
# Попутный замер 1 (шаг 9 брифа) — Q-6, пустые идентификаторы объекта (VIN).
# Имя системного поля SUBJ_AUTO_VIN — реальное наблюдение шага 7 T-0-8
# (reference/T-0-8_step7_charset_measurement_2026-08-17.md §2.e), не догадка.
# ---------------------------------------------------------------------------

VIN_FIELD_CATALOG = NamedQuery(
    name="vin_field_catalog",
    sql=(
        "SELECT ID, NAME, ID_OBJ_TABLE FROM DIR_CUSTOM_FIELDS "
        "WHERE NAME LIKE '%VIN%' OR NAME LIKE '%AUTO%'"
    ),
    note="шаг 9 подготовка: каталог кандидатов на поле идентификатора объекта (проверка, не смена SUBJ_AUTO_VIN на веру)",
)

# ВТОРАЯ правка (2026-08-18, реальный прогон шага 9): исходный `empty_vehicle_id_count`
# содержал ДВА независимых дефекта, найденных реальным прогоном, не офлайн-тестом.
#
# Дефект 1 — точное строковое совпадение `NAME = 'SUBJ_AUTO_VIN'` никогда не
# совпадает: реальное значение `DIR_CUSTOM_FIELDS.NAME` несёт обвязку
# `'&$DIR_CUSTOM_FIELDS.SUBJ_AUTO_VIN#&'` (шаблон системы, не голое имя) — вскрыто
# запросом `vin_field_catalog` того же прогона, который дал ДВЕ строки для этого
# поля: `(ID=12, ID_OBJ_TABLE=9)` и `(ID=22, ID_OBJ_TABLE=16)`. Подзапрос с точным
# совпадением возвращал NULL, `v.ID_FIELD = NULL` никогда не истинно, `LEFT JOIN`
# оставался пустым для ВСЕХ строк `SUBJECTS` — результат `EMPTY_VIN=TOTAL_SUBJECTS`
# (100%) был артефактом синтаксиса, не фактом о портфеле.
# Правка: использовать УЖЕ ИЗМЕРЕННЫЕ числовые ID (`12`, `22`) напрямую, без
# нового текстового совпадения по `NAME` вообще — устраняет класс ошибки целиком,
# не чинит конкретную строку шаблона (которая может ещё раз отличаться формой).
#
# Дефект 2 (потенциальный, не проверен фактом, но риск реален) — `ID_FIELD IN
# (12, 22)` внутри `LEFT JOIN` мог бы УМНОЖИТЬ строки `SUBJECTS`, если бы для
# одного `s.ID` совпадали ОБА `ID_FIELD` разом (`COUNT(*)` считал бы тогда
# join-строки, не объекты). Правка — `EXISTS`-подзапрос вместо `LEFT JOIN`:
# `TOTAL_SUBJECTS` — обычный счёт строк `SUBJECTS`, без всякого join;
# `EMPTY_VIN` — считает объект пустым, только если НИ ОДНОГО непустого значения
# нет НИ У ОДНОГО из двух `ID_FIELD`. Значение `ID_OBJ_TABLE` (9 vs 16) сюда не
# подставляется угадыванием — какая из двух записей относится к `SUBJECTS`,
# устанавливает отдельный диагностический запрос `tables_table_lookup` ниже;
# `EXISTS (... ID_FIELD IN (12, 22) ...)` работает корректно независимо от
# ответа: он не требует знать заранее, какой ID_FIELD "правильный", раз оба
# кандидата подставлены явно, измеренными числами, а не текстом.
TABLES_TABLE_LOOKUP = NamedQuery(
    name="tables_table_lookup",
    sql=(
        "SELECT ID, DBTABLE, TABLE_NAME, NAME_CATEG_DOCS, NAME_LOG_OBJ "
        "FROM TABLES_TABLE WHERE ID IN (9, 16)"
    ),
    note=(
        "диагностика шага 9: чему соответствуют ID_OBJ_TABLE=9 и 16 у двух "
        "найденных записей SUBJ_AUTO_VIN — не гадание, а измерение по "
        "справочнику таблиц, который уже входит в девять разрешённых"
    ),
)

VIN_FIELD_VALUES_EXISTENCE_CHECK = NamedQuery(
    name="vin_field_values_existence_check",
    sql=(
        "SELECT ID_FIELD, COUNT(*) AS CNT, "
        "SUM(CASE WHEN FIELD_VALUE IS NOT NULL AND TRIM(FIELD_VALUE) <> '' THEN 1 ELSE 0 END) AS NON_EMPTY_CNT "
        "FROM CUSTOM_FIELDS_VALUES WHERE ID_FIELD IN (12, 22) GROUP BY ID_FIELD"
    ),
    note=(
        "обратный контроль (ADR-033): считает непустые значения ПО ДВУМ уже "
        "измеренным ID_FIELD НАПРЯМУЮ из CUSTOM_FIELDS_VALUES, БЕЗ join на "
        "SUBJECTS — если тут NON_EMPTY_CNT > 0, а empty_vehicle_id_count всё "
        "равно даёт 100% пустых, значит дефект в join/связи с SUBJECTS, а не "
        "в данных; если тут тоже 0 — 100% пустых может оказаться реальным фактом"
    ),
)

EMPTY_VEHICLE_ID_COUNT = NamedQuery(
    name="empty_vehicle_id_count",
    sql=(
        "SELECT COUNT(*) AS TOTAL_SUBJECTS, "
        "SUM(CASE WHEN EXISTS ("
        "SELECT 1 FROM CUSTOM_FIELDS_VALUES v "
        "WHERE v.ID_OBJ = s.ID AND v.ID_FIELD IN (12, 22) "
        "AND v.FIELD_VALUE IS NOT NULL AND TRIM(v.FIELD_VALUE) <> ''"
        ") THEN 0 ELSE 1 END) AS EMPTY_VIN "
        "FROM SUBJECTS s"
    ),
    note=(
        "шаг 9 / Q-6 (ИСПРАВЛЕНО 2026-08-18): счёт объектов с пустым VIN через "
        "EXISTS по ДВУМ измеренным ID_FIELD (12, 22) — без текстового совпадения "
        "NAME (дефект 1) и без риска умножения строк LEFT JOIN (дефект 2). "
        "Доля считается вызывающим кодом: EMPTY_VIN / TOTAL_SUBJECTS."
    ),
)

# ---------------------------------------------------------------------------
# Попутный замер 2 (шаг 10 брифа) — Q-23, валюта и курс.
# ---------------------------------------------------------------------------

EXCHANGE_RATE_DISTRIBUTION = NamedQuery(
    name="exchange_rate_distribution",
    sql="SELECT EXCHANGE_RATE, COUNT(*) AS CNT FROM CONTRACTS GROUP BY EXCHANGE_RATE ORDER BY EXCHANGE_RATE",
    note="шаг 10 / Q-23: распределение EXCHANGE_RATE по группам договоров",
)

USE_EXCHANGE_FLAGS_DISTRIBUTION = NamedQuery(
    name="use_exchange_flags_distribution",
    sql=(
        "SELECT USE_EXCHANGE, USE_EXCHANGE_IF_INCREASE, COUNT(*) AS CNT "
        "FROM CONTRACTS_TERMS "
        "GROUP BY USE_EXCHANGE, USE_EXCHANGE_IF_INCREASE"
    ),
    note="шаг 10 / Q-23: распределение флагов применения курса",
)

# ---------------------------------------------------------------------------
# Попутный замер 3 (шаг 11 брифа, ADR-067) — сроки договоров.
# ---------------------------------------------------------------------------

CONTRACT_TERM_HISTOGRAM = NamedQuery(
    name="contract_term_histogram",
    sql=(
        "SELECT (PLAN_CLOSE_DATE - CONTRACT_DATE) AS TERM_DAYS, COUNT(*) AS CNT "
        "FROM CONTRACTS "
        "WHERE PLAN_CLOSE_DATE IS NOT NULL AND CONTRACT_DATE IS NOT NULL "
        "GROUP BY (PLAN_CLOSE_DATE - CONTRACT_DATE) "
        "ORDER BY TERM_DAYS"
    ),
    note="шаг 11: распределение срока договора (PLAN_CLOSE_DATE - CONTRACT_DATE) гистограммой по всему портфелю",
)

# ---------------------------------------------------------------------------
# Попутный замер 4 (шаг 12 брифа) — признак реализации / цена продажи; сырьё T-0-4b.
# ---------------------------------------------------------------------------

REALIZATION_FIELD_CATALOG = NamedQuery(
    name="realization_field_catalog",
    sql=(
        "SELECT ID, NAME, ID_OBJ_TABLE FROM DIR_CUSTOM_FIELDS "
        "WHERE NAME LIKE '%SALE%' OR NAME LIKE '%PRICE%' OR NAME LIKE '%REALIZ%' OR NAME LIKE '%SOLD%'"
    ),
    note="шаг 12: поиск в каталоге кастомных полей кандидата на 'цена продажи' — найдено/не найдено по результату, не по догадке",
)

CONTRACT_STATE_CATALOG = NamedQuery(
    name="contract_state_catalog",
    sql="SELECT STATE_ID, CODE, SORT_ORDER FROM CONTRACT_STATES ORDER BY SORT_ORDER",
    note="шаг 12: признак 'ушёл в реализацию' проверяется по CONTRACT_STATES.CODE (SALED/ONSALE уже видены шагом 7 T-0-8, здесь — полный каталог как факт, не пересказ)",
)

T0_4B_RAW_TERMS_AGGREGATES: tuple[NamedQuery, ...] = (
    NamedQuery(
        name="raw_is_pay_perc_on_future",
        sql="SELECT IS_PAY_PERC_ON_FUTURE, COUNT(*) AS CNT FROM CONTRACTS_TERMS GROUP BY IS_PAY_PERC_ON_FUTURE",
        note="сырьё T-0-4b (разбор не входит в T-0-4a)",
    ),
    NamedQuery(
        name="raw_start_moment",
        sql="SELECT START_MOMENT, COUNT(*) AS CNT FROM CONTRACTS_TERMS GROUP BY START_MOMENT",
        note="сырьё T-0-4b",
    ),
    NamedQuery(
        name="raw_id_op",
        sql="SELECT ID_OP, COUNT(*) AS CNT FROM CONTRACTS_TERMS GROUP BY ID_OP",
        note="сырьё T-0-4b",
    ),
    NamedQuery(
        name="raw_acc_pay_scheme",
        sql="SELECT ACC_PAY_SCHEME, COUNT(*) AS CNT FROM CONTRACTS_TERMS GROUP BY ACC_PAY_SCHEME",
        note="сырьё T-0-4b",
    ),
    NamedQuery(
        name="raw_exceed_days_months",
        sql=(
            "SELECT EXCEED_DAYS, EXCEED_MONTHS, COUNT(*) AS CNT "
            "FROM CONTRACTS_TERMS GROUP BY EXCEED_DAYS, EXCEED_MONTHS"
        ),
        note="сырьё T-0-4b",
    ),
    NamedQuery(
        name="raw_is_privilege_in_exceed_days",
        sql=(
            "SELECT IS_PRIVILEGE_IN_EXCEED_DAYS, COUNT(*) AS CNT "
            "FROM CONTRACTS_TERMS GROUP BY IS_PRIVILEGE_IN_EXCEED_DAYS"
        ),
        note="сырьё T-0-4b",
    ),
)

STATIC_QUERIES: tuple[NamedQuery, ...] = (
    ENGINE_VERSION,
    ROW_COUNT_CONTROL,
    OPERATIONS_STRUCTURE,
    OPERATION_TYPE_COUNTS,
    ACTIVE_TOTAL,
    REOPEN_ACTIVE_WITH_PREV,
    REOPEN_MAX_CHAIN_LENGTH,
    REOPEN_CHAIN_LENGTH_SATURATED_CHECK,
    REOPEN_CONTRACTS_IN_CHAINS,
    REOPEN_SAMPLE_PAIRS,
    VIN_FIELD_CATALOG,
    TABLES_TABLE_LOOKUP,
    VIN_FIELD_VALUES_EXISTENCE_CHECK,
    EMPTY_VEHICLE_ID_COUNT,
    EXCHANGE_RATE_DISTRIBUTION,
    USE_EXCHANGE_FLAGS_DISTRIBUTION,
    CONTRACT_TERM_HISTOGRAM,
    REALIZATION_FIELD_CATALOG,
    CONTRACT_STATE_CATALOG,
) + T0_4B_RAW_TERMS_AGGREGATES


# ---------------------------------------------------------------------------
# Шаги 7–8 брифа — зависят от кодов OP_VID, снятых ЖИВЫМ запросом
# `operations_structure`/`operation_type_counts` выше. Не угадываются здесь.
# ---------------------------------------------------------------------------


def build_renewal_op_queries(renewal_op_vids: Sequence[int]) -> tuple[NamedQuery, ...]:
    """Строит запросы ветви «Погашение» и сводной доли по СПИСКУ кодов OP_VID,
    которые по прочитанному на сервере описанию колонки означают продление или
    частичное погашение (шаг 5 брифа снимает описание, шаг 7 читает его и
    называет коды — код выбора не подставляет значение сам).

    `renewal_op_vids` пустой или не передан → `DiscoveryConfigError`, а не
    построение запроса с пустым `IN ()` (это была бы тихая подстановка
    "ничего не считать продлением", неотличимая от намеренного нуля)."""
    if not renewal_op_vids:
        raise DiscoveryConfigError(
            "CONTEXT GAP: renewal_op_vids пуст — коды OP_VID, означающие продление/"
            "частичное погашение, ещё не сняты запросом operations_structure/"
            "operation_type_counts на сервере. Подставлять значение угадыванием "
            "запрещено (anti-improvisation, CLAUDE.md)."
        )
    placeholders = ", ".join("?" for _ in renewal_op_vids)
    params = tuple(renewal_op_vids)

    repayment_active = NamedQuery(
        name="repayment_active_with_renewal_op",
        sql=(
            "SELECT COUNT(DISTINCT c.CONTRACT_ID) AS ACTIVE_WITH_RENEWAL_OP "
            "FROM CONTRACTS c "
            "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
            "JOIN OPERATIONS o ON o.DEPOSIT_ID = c.CONTRACT_ID "
            f"WHERE st.CODE = 'OPEN' AND o.OP_VID IN ({placeholders})"
        ),
        params=params,
        note="шаг 7: сколько активных договоров имеют хотя бы одну операцию из названных типов",
    )
    renewed_share = NamedQuery(
        name="renewed_portfolio_share",
        sql=(
            "SELECT COUNT(DISTINCT c.CONTRACT_ID) AS RENEWED_PORTFOLIO "
            "FROM CONTRACTS c "
            "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
            "LEFT JOIN OPERATIONS o ON o.DEPOSIT_ID = c.CONTRACT_ID "
            f"AND o.OP_VID IN ({placeholders}) "
            "WHERE st.CODE = 'OPEN' AND (c.ID_PREV_CONTRACT IS NOT NULL OR o.OP_ID IS NOT NULL)"
        ),
        params=params,
        note="шаг 8: объединение обеих ветвей — числитель доли перезакладываемых (знаменатель — active_total)",
    )
    return (repayment_active, renewed_share)


# ---------------------------------------------------------------------------
# Исполнение — печатает результат каждого запроса агрегатами, ничего не пишет
# кроме лога.
# ---------------------------------------------------------------------------


def run_query(connection: Any, nq: NamedQuery) -> list[tuple]:
    rows = access_point(connection, nq.sql, nq.params)
    logger.info("замер [%s] (%s): %d строк(и)", nq.name, nq.note, len(rows))
    printed = rows[:_MAX_ROWS_PRINTED]
    for row in printed:
        logger.info("  %s: %r", nq.name, row)
    if len(rows) > _MAX_ROWS_PRINTED:
        logger.info(
            "  %s: ещё %d строк(и) не напечатано (обрезка на %d — агрегат этой "
            "задачи не должен быть больше)",
            nq.name,
            len(rows) - _MAX_ROWS_PRINTED,
            _MAX_ROWS_PRINTED,
        )
    return rows


def print_reopen_pairs(rows: list[tuple]) -> None:
    """Печатает пары 'старый -> новый' ПОРЯДКОВЫМ номером выборки — запрос
    `reopen_sample_pairs` не возвращает ни CONTRACT_ID, ни CONTRACT_NUM,
    поэтому даже прямая печать строки результата номера договора не несёт."""
    for i, (new_date, prev_date) in enumerate(rows, start=1):
        logger.info("  пара #%d: %s -> %s", i, prev_date, new_date)


def run_static(connection: Any) -> dict[str, list[tuple]]:
    """Прогоняет все запросы, не зависящие от результата шага 5 (`STATIC_QUERIES`).
    Запросы шагов 7–8 (ветвь «Погашение») исполняются ОТДЕЛЬНЫМ вызовом
    `build_renewal_op_queries()` после того, как коды OP_VID названы по
    результату `operations_structure`/`operation_type_counts` этого прогона."""
    results: dict[str, list[tuple]] = {}
    for nq in STATIC_QUERIES:
        rows = run_query(connection, nq)
        results[nq.name] = rows
        if nq.name == "reopen_sample_pairs":
            print_reopen_pairs(rows)
    return results


def run_renewal_ops(connection: Any, renewal_op_vids: Sequence[int]) -> dict[str, list[tuple]]:
    results: dict[str, list[tuple]] = {}
    for nq in build_renewal_op_queries(renewal_op_vids):
        results[nq.name] = run_query(connection, nq)
    return results


# ---------------------------------------------------------------------------
# CLI (шаги 3+ брифа, класс B — исполняется на сервере ERP ТОЛЬКО после
# отдельной карточки подтверждения владельца НА КАЖДЫЙ вызов).
#
# «Один скрипт на ШАГ брифа, а не на команду» (`05_CONVENTIONS §I`): один и тот
# же файл вызывается на сервере НЕСКОЛЬКО раз, но каждый вызов исполняет СВОЙ
# список запросов, соответствующий ровно одному шагу брифа (например, шаг 4 —
# только engine_version,row_count_control; шаг 5 — только operations_structure,
# operation_type_counts), и каждый такой вызов — отдельное действие класса B со
# своей карточкой. Пустой или неизвестный список отбивается `DiscoveryConfigError`
# ДО открытия соединения с базой — не молчаливый прогон всего подряд.
#
# **Источник списка — ДВА способа, оба ведут к одному и тому же аргументу.**
# (1) `--queries` явным текстом — способ офлайн-тестов и ручных прогонов, не
# меняется. (2) Если `--queries` не передан — читается ИЗ ФАЙЛА, путь по
# умолчанию `DEFAULT_QUERIES_FILE` ниже, переопределимый `--queries-file`.
# Появилось 2026-08-18: `schtasks /change /tr` для password-based задачи
# планировщика на каждую смену шага брифа требует пароль учётки заново
# (реальное ограничение Windows Task Scheduler, не наша прихоть) — Task
# Scheduler хранит логон-креды для конкретного зафиксированного `/tr`,
# смена аргументов командной строки есть смена `/tr`. Файл-конфиг убирает
# необходимость трогать пароль `lombard-agent-svc` и вызывать `schtasks
# /change` на каждом шаге: `/tr` фиксируется РАЗ на всю оставшуюся задачу,
# между шагами меняется только СОДЕРЖИМОЕ файла (доставка без пароля, тем
# же каналом base64+certutil, что и код), и `schtasks /run` без `/change`.
# Пустой или отсутствующий файл — `DiscoveryConfigError`, а не «ничего не
# делать молча» (та же дисциплина, что у пустого `--queries`).
# ---------------------------------------------------------------------------

DEFAULT_QUERIES_FILE = r"C:\LombardAgent\control\t0_4a_next_queries.txt"
# Тот же приём для кодов OP_VID шагов 7-8 (2026-08-18): без файла — фиксация
# /tr задачи планировщика на шаг 7 потребовала бы обратно schtasks /change,
# ровно то, от чего избавлялись. НЕОБЯЗАТЕЛЬНЫЙ, в отличие от файла запросов:
# отсутствие означает «этот вызов не касается динамических запросов шагов
# 7-8» (тот же смысл, что у пустого --renewal-op-vids раньше), а не CONTEXT GAP —
# CONTEXT GAP наступает позже и по-другому: build_renewal_op_queries() уже
# отказывает пустым списком, если вызывающий вправду просит динамическое имя.
DEFAULT_RENEWAL_OP_VIDS_FILE = r"C:\LombardAgent\control\t0_4a_renewal_op_vids.txt"


def _open_connection_like_run_daily() -> Any:
    """Открывает подключение к Firebird ТЕМ ЖЕ способом, что `run_daily.py`
    (шаг 1 брифа: «переписывать механизм подключения не нужно и не следует»).
    Импортирует приватные функции того модуля вместо дублирования логики —
    тот же принцип добавления поверх существующего кода, что `ADR-050` п.10
    применил к `run_daily.py` относительно `agent.py`."""
    from connector.agent import run_daily

    run_daily._refresh_jwt()
    credential_value = run_daily._fetch_db_credential_value()
    return run_daily._connect_firebird(credential_value)


def _resolve_queries(
    names: Sequence[str], renewal_op_vids: Sequence[int]
) -> list[NamedQuery]:
    static_by_name = {q.name: q for q in STATIC_QUERIES}
    dynamic_by_name = (
        {q.name: q for q in build_renewal_op_queries(renewal_op_vids)}
        if renewal_op_vids
        else {}
    )
    unknown = [n for n in names if n not in static_by_name and n not in dynamic_by_name]
    if unknown:
        known = sorted(set(static_by_name) | set(dynamic_by_name))
        raise DiscoveryConfigError(
            f"CONTEXT GAP: --queries называет неизвестные имена {unknown!r} — "
            f"известные имена этого вызова: {known!r}. Имя не угадывается."
        )
    return [static_by_name.get(n) or dynamic_by_name[n] for n in names]


def _read_control_value(
    explicit: str | None,
    file_path: str | None,
    default_file: str,
    *,
    required: bool,
    what: str,
) -> str:
    """Общий читатель «явное значение ЛИБО control-файл» для `--queries` и
    `--renewal-op-vids`. `required=True` (список запросов) — отсутствие или
    пустота файла есть `DiscoveryConfigError`, значение не подставляется
    молчанием. `required=False` (коды OP_VID) — отсутствие файла означает
    «этот вызов их не касается» и возвращает пустую строку, дальнейший отказ
    (если имя запроса всё-таки динамическое) кидает `build_renewal_op_queries`
    самостоятельно на пустом списке — двойной защиты не заводим."""
    if explicit:
        return explicit

    path = Path(file_path or default_file)
    if not path.exists():
        if required:
            raise DiscoveryConfigError(
                f"CONTEXT GAP: {what} не передан явно, и control-файл {path} не "
                "существует — значение не названо ни одним из двух источников. "
                "Не подставляется."
            )
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content and required:
        raise DiscoveryConfigError(
            f"CONTEXT GAP: control-файл {path} существует, но пуст после "
            f"strip() — {what} не назван"
        )
    return content


def _read_queries_spec(args: Any) -> str:
    """Возвращает СЫРОЙ (не разобранный на имена) текст списка запросов —
    из `--queries`, если передан явно, иначе из файла (`--queries-file` или
    `DEFAULT_QUERIES_FILE`). Обязательный вход (`required=True`)."""
    return _read_control_value(
        args.queries, args.queries_file, DEFAULT_QUERIES_FILE, required=True, what="--queries"
    )


def _read_renewal_op_vids_spec(args: Any) -> str:
    """То же самое для кодов `OPERATIONS.OP_VID` шагов 7-8 — НЕОБЯЗАТЕЛЬНЫЙ
    вход (`required=False`): большинство шагов их не используют вовсе."""
    return _read_control_value(
        args.renewal_op_vids or None,
        args.renewal_op_vids_file,
        DEFAULT_RENEWAL_OP_VIDS_FILE,
        required=False,
        what="--renewal-op-vids",
    )


def cli_main(argv: Sequence[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "T-0-4a: запуск ИМЕНОВАННОГО подмножества запросов модуля через "
            "access_point(). Список закрывает ровно ОДИН шаг брифа за вызов — "
            "не общий 'прогнать всё'. Источник списка — --queries явным текстом "
            "ЛИБО (если --queries не передан) control-файл — см. --queries-file."
        )
    )
    parser.add_argument(
        "--queries",
        default=None,
        help=(
            "запятая-разделённый список имён запросов (STATIC_QUERIES или "
            "динамических); если не передан — читается из control-файла"
        ),
    )
    parser.add_argument(
        "--queries-file",
        default=None,
        help=(
            "путь к control-файлу со списком имён (одна строка, через запятую); "
            f"используется, только если --queries не передан; по умолчанию "
            f"{DEFAULT_QUERIES_FILE}"
        ),
    )
    parser.add_argument(
        "--renewal-op-vids",
        default="",
        help=(
            "запятая-разделённые коды OPERATIONS.OP_VID для запросов шагов 7-8 "
            "(repayment_active_with_renewal_op, renewed_portfolio_share); "
            "пусто/не передан — читается из control-файла (--renewal-op-vids-file), "
            "а если и файла нет — считается, что вызов их не касается"
        ),
    )
    parser.add_argument(
        "--renewal-op-vids-file",
        default=None,
        help=(
            "путь к control-файлу с кодами OP_VID (одна строка, через запятую); "
            f"по умолчанию {DEFAULT_RENEWAL_OP_VIDS_FILE}; НЕОБЯЗАТЕЛЕН — в "
            "отличие от --queries-file, отсутствие не CONTEXT GAP"
        ),
    )
    args = parser.parse_args(list(argv))

    raw_spec = _read_queries_spec(args)
    names = [n.strip() for n in raw_spec.split(",") if n.strip()]
    if not names:
        raise DiscoveryConfigError("CONTEXT GAP: список запросов пуст после разбора — какой шаг исполнять, не названо")
    raw_renewal = _read_renewal_op_vids_spec(args)
    renewal_op_vids = tuple(int(v) for v in raw_renewal.split(",") if v.strip())

    queries = _resolve_queries(names, renewal_op_vids)

    connection = _open_connection_like_run_daily()
    try:
        for nq in queries:
            rows = run_query(connection, nq)
            if nq.name == "reopen_sample_pairs":
                print_reopen_pairs(rows)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    try:
        sys.exit(cli_main(sys.argv[1:]))
    except DiscoveryConfigError as exc:
        logger.error("%s", exc)
        sys.exit(2)
