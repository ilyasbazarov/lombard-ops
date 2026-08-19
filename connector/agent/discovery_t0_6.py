"""
connector/agent/discovery_t0_6.py — T-0-6, шаг 1 (класс A, локально)

Модуль замера для брифа `briefs/T-0-6.md`. Каждый запрос идёт через единственную
точку доступа (`connector.agent.access_point.access_point`) — здесь нет ни одного
`cursor.execute` напрямую и ни одного второго пути к базе PawnShop. Устройство —
то же, что `discovery_t0_4a.py` (образец брифа): фиксированный текст в
`STATIC_QUERIES`, проверяемый оффлайн-тестом целиком, плюс один класс запросов,
зависящий от результата другого запроса того же модуля (`vehicle_field_value_counts`
зависит от `ID_FIELD`, найденных `vehicle_field_candidates` — тот же приём, что
`build_renewal_op_queries` в `discovery_t0_4a.py` для `OP_VID`).

**Подключение** открывается CLI (`cli_main`, ниже) ТЕМ ЖЕ способом, что в
`run_daily.py`/`discovery_t0_4a.py` — реюзом приватных функций `run_daily`
(`_refresh_jwt`, `_fetch_db_credential_value`, `_connect_firebird`), второй
механизм не пишется.

**Класс исполнения.** Написание и импорт этого файла — класс A (код без
применения). Реальный запуск CLI ПРОТИВ БОЕВОЙ БАЗЫ — класс B: каждый вызов на
сервере ERP исполняется только после отдельной карточки подтверждения владельца
(шаги 3 и далее брифа `T-0-6`), и вызов охватывает РОВНО ОДИН шаг брифа
(`--queries` называет его именованные запросы явно) — не «прогнать всё».

**Санитария (`ADR-039`, дословно из брифа).** Каждый запрос ниже — агрегат
(счёт, группировка, распределение) либо каталог метаданных (`DIR_CUSTOM_FIELDS`:
имена/типы полей, не значения строк клиентов); пары «старый → новый» здесь не
используются (это был предмет `T-0-4a`). Ни один запрос не выбирает номер
договора, имя человека или VIN как значение строки.

**Таблицы** — исключительно из `ALLOWED_TABLES` (`access_point.py`) плюс
системные `RDB$*`; попытка обратиться к таблице вне списка отбивается
`validate_query` ДО отправки на сервер — гарантия точки доступа, не этого модуля.

**`active` в этом модуле = `CONTRACT_STATES.CODE = 'OPEN'`** — то же определение,
что уже закрыло `Q-7`/`Q-8` (`ADR-042`) и что использовал `discovery_t0_4a.py`
(`active_total`). Здесь не переопределяется заново.

**`DIR_CUSTOM_FIELDS.NAME` — шаблон, не голое имя** (`11_INFRA_FACTS.md`,
замер `T-0-4a`): реальное значение несёт системную обвязку вида
`'&$DIR_CUSTOM_FIELDS.SUBJ_AUTO_VIN#&'`. Поиск здесь — намеренно ШИРОКИЙ набор
`LIKE`-фрагментов (не одна догадка на поле): цель шага — печатать ВСЕ совпавшие
строки с `ID_FIELD`, а не заранее угадать единственное верное имя. Отбор
верного `ID_FIELD` из напечатанного списка — работа шага 9 брифа (по ненулевому
счёту `vehicle_field_value_counts`), не этого запроса.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# Тот же приём, что `run_daily.py`/`discovery_t0_4a.py` (`connector/agent/<файл>.py`):
# при запуске ПРЯМО как скрипт абсолютным путём интерпретатор кладёт в
# `sys.path[0]` каталог САМОГО файла, а не корень репозитория — импорт
# `connector.agent.access_point` тогда падает `ModuleNotFoundError`. Найдено
# реальным прогоном `T-0-4a` 2026-08-18, решение то же и здесь.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from connector.agent.access_point import access_point  # noqa: E402

logger = logging.getLogger("lombard.agent.discovery_t0_6")

# Порог печати строк на запрос — тот же приём, что `discovery_t0_4a.py`:
# агрегаты этой задачи по конструкции малы, а `vehicle_field_candidates`
# (широкий LIKE-поиск) специально ограничен FIRST 200 в самом SQL как страховка
# от неожиданно большого совпадения.
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
# величина приёмки получается автоматически).
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
# Шаг 5 брифа — распределение по статусам и аномалии.
# ---------------------------------------------------------------------------

ACTIVE_STATUS_DISTRIBUTION = NamedQuery(
    name="active_status_distribution",
    sql=(
        "SELECT st.CODE AS STATE_CODE, COUNT(*) AS CNT "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "GROUP BY st.CODE "
        "ORDER BY st.CODE"
    ),
    note=(
        "счёт активных договоров И распределение по статусам ОДНИМ запросом: "
        "'активные' = строка CODE='OPEN' в этом же распределении (то же "
        "определение, что active_total у T-0-4a, Q-7/Q-8, ADR-042) — вторая "
        "выдумка счётчика не заводится"
    ),
)

# Бакеты порогов 03 §1 повторены дословно из смещений (attention=-6, overdue=+2,
# premarketing=+16, realization=+32) — CASE повторён в GROUP BY (Firebird 2.5
# не гарантирует GROUP BY по алиасу для вычисляемого выражения).
_OFFSET_BUCKET_CASE = (
    "CASE "
    "WHEN (CURRENT_DATE - c.PLAN_CLOSE_DATE) <= -7 THEN '1_le_-7' "
    "WHEN (CURRENT_DATE - c.PLAN_CLOSE_DATE) BETWEEN -6 AND 1 THEN '2_-6..+1' "
    "WHEN (CURRENT_DATE - c.PLAN_CLOSE_DATE) BETWEEN 2 AND 15 THEN '3_+2..+15' "
    "WHEN (CURRENT_DATE - c.PLAN_CLOSE_DATE) BETWEEN 16 AND 31 THEN '4_+16..+31' "
    "ELSE '5_ge_+32' "
    "END"
)

ACTIVE_OFFSET_DISTRIBUTION = NamedQuery(
    name="active_offset_distribution",
    sql=(
        f"SELECT {_OFFSET_BUCKET_CASE} AS BUCKET, COUNT(*) AS CNT "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "WHERE st.CODE = 'OPEN' AND c.PLAN_CLOSE_DATE IS NOT NULL "
        f"GROUP BY {_OFFSET_BUCKET_CASE} "
        "ORDER BY BUCKET"
    ),
    note=(
        "распределение (today - PLAN_CLOSE_DATE) активных договоров по бакетам "
        "порогов 03 §1: -7 и раньше / -6..+1 / +2..+15 / +16..+31 / +32 и далее. "
        "PLAN_CLOSE_DATE IS NULL исключены здесь — их считает отдельно "
        "anomaly_empty_plan_close_date, чтобы не смешивать два класса аномалии"
    ),
)

ANOMALY_EMPTY_PLAN_CLOSE_DATE = NamedQuery(
    name="anomaly_empty_plan_close_date",
    sql=(
        "SELECT COUNT(*) AS EMPTY_PLAN_CLOSE_DATE "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "WHERE st.CODE = 'OPEN' AND c.PLAN_CLOSE_DATE IS NULL"
    ),
    note="ADR-070, класс аномалии 1: активный договор с пустой PLAN_CLOSE_DATE — статус невычислим",
)

ANOMALY_NONPOSITIVE_TERM = NamedQuery(
    name="anomaly_nonpositive_term",
    sql=(
        "SELECT COUNT(*) AS NONPOSITIVE_TERM "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "WHERE st.CODE = 'OPEN' AND c.PLAN_CLOSE_DATE IS NOT NULL "
        "AND c.CONTRACT_DATE IS NOT NULL "
        "AND (c.PLAN_CLOSE_DATE - c.CONTRACT_DATE) <= 0"
    ),
    note="ADR-070, класс аномалии 2: активный договор с PLAN_CLOSE_DATE - CONTRACT_DATE <= 0",
)

ANOMALY_RENEWAL_WITHOUT_PREDECESSOR = NamedQuery(
    name="anomaly_renewal_without_predecessor",
    sql=(
        "SELECT COUNT(*) AS RENEWAL_WITHOUT_PREDECESSOR "
        "FROM CONTRACTS c "
        "WHERE c.ID_PREV_CONTRACT IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM CONTRACTS p WHERE p.CONTRACT_ID = c.ID_PREV_CONTRACT) "
        "AND NOT EXISTS (SELECT 1 FROM OPERATIONS o WHERE o.DEPOSIT_ID = c.CONTRACT_ID AND o.OP_VID = 0)"
    ),
    note=(
        "договор отмечен признаком продления через ID_PREV_CONTRACT, но "
        "ссылка не резолвится в реальную строку CONTRACTS (пустой/битый "
        "предшественник), И при этом нет операции OP_VID=0 (ovPay), которая "
        "иначе легитимно объясняла бы признак продления другой веткой. Дословно "
        "по шагу 1 брифа, без ограничения по статусу — брифом не указано"
    ),
)

# ---------------------------------------------------------------------------
# Шаг 6 брифа — срок договора по активным, в разрезе продлений.
# ---------------------------------------------------------------------------

_IS_RENEWAL_CASE = (
    "CASE WHEN c.ID_PREV_CONTRACT IS NOT NULL "
    "OR EXISTS (SELECT 1 FROM OPERATIONS o WHERE o.DEPOSIT_ID = c.CONTRACT_ID AND o.OP_VID = 0) "
    "THEN 1 ELSE 0 END"
)

ACTIVE_TERM_HISTOGRAM = NamedQuery(
    name="active_term_histogram",
    sql=(
        "WITH sub AS ("
        "SELECT (c.PLAN_CLOSE_DATE - c.CONTRACT_DATE) AS TERM_DAYS, "
        f"{_IS_RENEWAL_CASE} AS IS_RENEWAL "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "WHERE st.CODE = 'OPEN' AND c.PLAN_CLOSE_DATE IS NOT NULL "
        "AND c.CONTRACT_DATE IS NOT NULL"
        ") "
        "SELECT TERM_DAYS, IS_RENEWAL, COUNT(*) AS CNT FROM sub "
        "GROUP BY TERM_DAYS, IS_RENEWAL "
        "ORDER BY TERM_DAYS"
    ),
    note=(
        "распределение срока PLAN_CLOSE_DATE-CONTRACT_DATE ПО АКТИВНЫМ, "
        "отдельно по признаку продления (обе ветви, OR) — снимает ADR-070 "
        "уточнение 1 (T-0-4a мерил по всей истории, не по активным). "
        "GROUP BY через WITH-CTE: Firebird 2.5 (SQLCODE -104) отбил повтор "
        "коррелированного EXISTS внутри CASE прямо в GROUP BY — измерено "
        "реальным прогоном 2026-08-19; derived-table `FROM (SELECT...) sub` "
        "тоже не годится — validate_query распознаёт таблицы только из "
        "FROM/JOIN дерева токенов, алиас производной таблицы читает как имя "
        "таблицы вне списка, а CTE-имена исключает явно (_cte_names) — тот "
        "же класс сборки, что и White-list, починка со стороны запроса"
    ),
)

# ---------------------------------------------------------------------------
# Шаг 7 брифа — renewal_share_active и гипотеза 44%.
# ---------------------------------------------------------------------------

RENEWAL_SHARE_ACTIVE = NamedQuery(
    name="renewal_share_active",
    sql=(
        "SELECT COUNT(DISTINCT c.CONTRACT_ID) AS RENEWED_ACTIVE, "
        "(SELECT COUNT(*) FROM CONTRACTS cc "
        "JOIN CONTRACT_STATES st2 ON st2.STATE_ID = cc.CONTRACT_STATE "
        "WHERE st2.CODE = 'OPEN') AS ACTIVE_TOTAL "
        "FROM CONTRACTS c "
        "JOIN CONTRACT_STATES st ON st.STATE_ID = c.CONTRACT_STATE "
        "LEFT JOIN OPERATIONS o ON o.DEPOSIT_ID = c.CONTRACT_ID AND o.OP_VID = 0 "
        "WHERE st.CODE = 'OPEN' AND (c.ID_PREV_CONTRACT IS NOT NULL OR o.OP_ID IS NOT NULL)"
    ),
    note=(
        "доля активных договоров в цепочке продления (OR обеих ветвей), "
        "числитель и знаменатель одним прогоном на дату — 03 §2, строка "
        "renewal_share_active"
    ),
)

OP_VID0_DISTINCT_CONTRACTS = NamedQuery(
    name="op_vid0_distinct_contracts",
    sql=(
        "SELECT "
        "(SELECT COUNT(DISTINCT DEPOSIT_ID) FROM OPERATIONS WHERE OP_VID = 0) AS DISTINCT_WITH_OP_VID0, "
        "(SELECT COUNT(*) FROM CONTRACTS) AS TOTAL_CONTRACTS "
        "FROM RDB$DATABASE"
    ),
    note=(
        "различающая проверка гипотезы 44%: счёт РАЗЛИЧНЫХ договоров с "
        "операцией OP_VID=0, отнесённый к счёту договоров — сверка с 1111/2509 "
        "из T-0-4a (там считались операции, не различные договоры)"
    ),
)

# ---------------------------------------------------------------------------
# Шаг 8 брифа — поля объекта: марка, модель, год, госномер.
# ---------------------------------------------------------------------------

# DIR_CUSTOM_FIELDS.NAME — шаблон, не голое имя (11_INFRA_FACTS.md, T-0-4a).
# Поиск намеренно широкий: не одна догадка на категорию, а несколько
# правдоподобных английских фрагментов на категорию (портфель уже показал
# конвенцию SUBJ_AUTO_<ИМЯ> на примере VIN) — печатаются ВСЕ совпадения,
# отбор верного ID_FIELD делает следующий шаг по ненулевому счёту значений,
# а не этот запрос.
VEHICLE_FIELD_CANDIDATES = NamedQuery(
    name="vehicle_field_candidates",
    sql=(
        "SELECT FIRST 200 ID, NAME, ID_OBJ_TABLE FROM DIR_CUSTOM_FIELDS "
        "WHERE NAME LIKE '%MARK%' OR NAME LIKE '%BRAND%' "
        "OR NAME LIKE '%MODEL%' "
        "OR NAME LIKE '%YEAR%' OR NAME LIKE '%GOD%' "
        "OR NAME LIKE '%NUM%' OR NAME LIKE '%GOSNOM%' OR NAME LIKE '%REG%' "
        "OR NAME LIKE '%PLATE%'"
    ),
    note=(
        "каталог кандидатов на марку/модель/год/госномер — LIKE-фрагменты "
        "MARK/BRAND (марка), MODEL (модель), YEAR/GOD (год), "
        "NUM/GOSNOM/REG/PLATE (госномер); печатаются ВСЕ совпавшие строки с "
        "ID_FIELD, не только отобранные (критерий приёмки брифа)"
    ),
)


def build_vehicle_field_value_counts(id_fields: Sequence[int]) -> NamedQuery:
    """Строит запрос счёта непустых значений по СПИСКУ `ID_FIELD`, найденных
    запросом `vehicle_field_candidates` на сервере (шаг 8 брифа читает
    результат предыдущего запроса и называет найденные ID явно — код не
    подставляет их угадыванием, тот же приём, что `build_renewal_op_queries`
    в `discovery_t0_4a.py` для `OP_VID`).

    `id_fields` пустой или не передан → `DiscoveryConfigError`, а не запрос с
    пустым `IN ()` (тихая подстановка "ничего не найдено")."""
    if not id_fields:
        raise DiscoveryConfigError(
            "CONTEXT GAP: id_fields пуст — ID_FIELD полей марки/модели/года/"
            "госномера ещё не сняты запросом vehicle_field_candidates на "
            "сервере. Подставлять значение угадыванием запрещено "
            "(anti-improvisation, CLAUDE.md)."
        )
    placeholders = ", ".join("?" for _ in id_fields)
    params = tuple(id_fields)
    return NamedQuery(
        name="vehicle_field_value_counts",
        sql=(
            "SELECT ID_FIELD, COUNT(*) AS CNT, "
            "SUM(CASE WHEN FIELD_VALUE IS NOT NULL AND TRIM(FIELD_VALUE) <> '' THEN 1 ELSE 0 END) AS NON_EMPTY_CNT "
            f"FROM CUSTOM_FIELDS_VALUES WHERE ID_FIELD IN ({placeholders}) "
            "GROUP BY ID_FIELD"
        ),
        params=params,
        note=(
            "шаг 8: по каждому найденному ID_FIELD — счёт непустых значений в "
            "CUSTOM_FIELDS_VALUES. Поле с NON_EMPTY_CNT=0 полем-источником не "
            "является (критерий приёмки брифа)"
        ),
    )


STATIC_QUERIES: tuple[NamedQuery, ...] = (
    ENGINE_VERSION,
    ROW_COUNT_CONTROL,
    ACTIVE_STATUS_DISTRIBUTION,
    ACTIVE_OFFSET_DISTRIBUTION,
    ANOMALY_EMPTY_PLAN_CLOSE_DATE,
    ANOMALY_NONPOSITIVE_TERM,
    ANOMALY_RENEWAL_WITHOUT_PREDECESSOR,
    ACTIVE_TERM_HISTOGRAM,
    RENEWAL_SHARE_ACTIVE,
    OP_VID0_DISTINCT_CONTRACTS,
    VEHICLE_FIELD_CANDIDATES,
)


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
            "  %s: ещё %d строк(и) не напечатано (обрезка на %d)",
            nq.name,
            len(rows) - _MAX_ROWS_PRINTED,
            _MAX_ROWS_PRINTED,
        )
    return rows


def run_static(connection: Any) -> dict[str, list[tuple]]:
    """Прогоняет все запросы, не зависящие от результата другого запроса этого
    же модуля (`STATIC_QUERIES`). `vehicle_field_value_counts` исполняется
    ОТДЕЛЬНЫМ вызовом `build_vehicle_field_value_counts()` после того, как
    ID_FIELD названы по результату `vehicle_field_candidates` этого прогона."""
    results: dict[str, list[tuple]] = {}
    for nq in STATIC_QUERIES:
        results[nq.name] = run_query(connection, nq)
    return results


# ---------------------------------------------------------------------------
# CLI (шаги 3+ брифа, класс B — исполняется на сервере ERP ТОЛЬКО после
# отдельной карточки подтверждения владельца НА КАЖДЫЙ вызов).
#
# «Один скрипт на ШАГ брифа, а не на команду» (`05_CONVENTIONS §I`): тот же
# файл вызывается на сервере НЕСКОЛЬКО раз, каждый вызов исполняет СВОЙ список
# запросов, соответствующий ровно одному шагу брифа, каждый вызов — отдельное
# действие класса B со своей карточкой.
#
# Источник списка запросов — ДВА способа (тот же приём, что T-0-4a,
# 2026-08-18: `schtasks /change /tr` требует пароль заново при каждой смене
# аргументов у password-based задачи планировщика). `--queries` явным текстом
# ЛИБО — если не передан — control-файл, путь по умолчанию `DEFAULT_QUERIES_FILE`.
# ---------------------------------------------------------------------------

DEFAULT_QUERIES_FILE = r"C:\LombardAgent\control\t0_6_next_queries.txt"
# Тот же приём для найденных ID_FIELD (шаг 8): НЕОБЯЗАТЕЛЬНЫЙ control-файл —
# отсутствие означает «этот вызов не касается vehicle_field_value_counts», не
# CONTEXT GAP; CONTEXT GAP наступает позже — build_vehicle_field_value_counts()
# уже отказывает пустым списком, если вызывающий вправду просит это имя.
DEFAULT_ID_FIELDS_FILE = r"C:\LombardAgent\control\t0_6_id_fields.txt"


def _open_connection_like_run_daily() -> Any:
    """Открывает подключение к Firebird ТЕМ ЖЕ способом, что `run_daily.py`/
    `discovery_t0_4a.py` (шаг 1 брифа: «переписывать механизм подключения не
    нужно и не следует»)."""
    from connector.agent import run_daily

    run_daily._refresh_jwt()
    credential_value = run_daily._fetch_db_credential_value()
    return run_daily._connect_firebird(credential_value)


def _resolve_queries(names: Sequence[str], id_fields: Sequence[int]) -> list[NamedQuery]:
    static_by_name = {q.name: q for q in STATIC_QUERIES}
    dynamic_by_name = (
        {"vehicle_field_value_counts": build_vehicle_field_value_counts(id_fields)}
        if id_fields
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
    """Общий читатель «явное значение ЛИБО control-файл», тот же приём, что
    `discovery_t0_4a.py`. `required=True` (список запросов) — отсутствие или
    пустота файла есть `DiscoveryConfigError`. `required=False` (ID_FIELD) —
    отсутствие файла означает «этот вызов их не касается»."""
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
    return _read_control_value(
        args.queries, args.queries_file, DEFAULT_QUERIES_FILE, required=True, what="--queries"
    )


def _read_id_fields_spec(args: Any) -> str:
    return _read_control_value(
        args.id_fields or None,
        args.id_fields_file,
        DEFAULT_ID_FIELDS_FILE,
        required=False,
        what="--id-fields",
    )


def cli_main(argv: Sequence[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "T-0-6: запуск ИМЕНОВАННОГО подмножества запросов модуля через "
            "access_point(). Список закрывает ровно ОДИН шаг брифа за вызов — "
            "не общий 'прогнать всё'. Источник списка — --queries явным текстом "
            "ЛИБО (если --queries не передан) control-файл — см. --queries-file."
        )
    )
    parser.add_argument("--queries", default=None)
    parser.add_argument("--queries-file", default=None)
    parser.add_argument(
        "--id-fields",
        default="",
        help=(
            "запятая-разделённые ID_FIELD для vehicle_field_value_counts; "
            "пусто/не передан — читается из control-файла (--id-fields-file), "
            "а если и файла нет — считается, что вызов их не касается"
        ),
    )
    parser.add_argument("--id-fields-file", default=None)
    args = parser.parse_args(list(argv))

    raw_spec = _read_queries_spec(args)
    names = [n.strip() for n in raw_spec.split(",") if n.strip()]
    if not names:
        raise DiscoveryConfigError("CONTEXT GAP: список запросов пуст после разбора — какой шаг исполнять, не названо")
    raw_id_fields = _read_id_fields_spec(args)
    id_fields = tuple(int(v) for v in raw_id_fields.split(",") if v.strip())

    queries = _resolve_queries(names, id_fields)

    connection = _open_connection_like_run_daily()
    try:
        for nq in queries:
            run_query(connection, nq)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        sys.exit(cli_main(sys.argv[1:]))
    except DiscoveryConfigError as exc:
        logger.error("%s", exc)
        sys.exit(2)
