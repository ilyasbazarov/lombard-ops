reference/T-0-8_step7_agent_run_2026-08-17.md

# T-0-8 · Шаг 7 — основной прогон агента, ПРЕДЪЯВЛЕН · 2026-08-17

**Объект замера определён:** служба `LombardAgentDailyRun` на сервере ERP (`11_INFRA_FACTS.md`,
строка «Способ запуска агента») и код агента в `connector/agent/`, оба существовали до этой сессии.

**Кем исполнено:** владелец (Ilyas), по RDP на сервере ERP, запуск задачи планировщика по требованию
(`schtasks /run`), 2026-08-17. Эта сессия (класс A для чтения лога, класс B для чтения бакета)
фиксирует факт уже исполненного действия по предъявленному владельцем логу и по собственному чтению
объектов бакета — не запускает агента сама.

**Закрывает:** работу 1 передачи `reference/T-0-8_step7_handoff_executor_2026-08-17.md` §3; вместе с
`reference/T-0-8_step7_negative_probes_2026-08-17.md` закрывает шаг 7 брифа `briefs/T-0-8.md` целиком.

---

## 1. Вердикт по критериям приёмки шага 7

| Требование брифа | Предъявлено | Исход |
|---|---|---|
| Лог с напечатанным текстом каждого запроса | раздел 2 ниже — 9 текстов `SELECT`, дословно | **ПРОЙДЕНО** |
| Строка признака режима транзакции | `MON$READ_ONLY=1`, положительный факт, на каждый запрос | **ПРОЙДЕНО** |
| Отпечаток схемы | `GUARD: отпечаток всех 9 таблиц совпал с эталоном` | **ПРОЙДЕНО** |
| `gcloud storage ls` с созданным объектом в бакете | раздел 3 ниже — 9 объектов, выполнено этой сессией | **ПРОЙДЕНО** |
| Число строк выгрузки | раздел 4 ниже — построчно из лога | **ПРОЙДЕНО** |
| Отрицательный случай в реальном прогоне | закрыт ОТДЕЛЬНЫМ артефактом (см. «Что этим артефактом НЕ закрыто» ниже) | **ПРОЙДЕНО отдельно** |

## 2. Лог прогона — дословно

Источник: `C:\LombardAgent\logs\run_daily_20260817_181717.err.log` (17177 байт, 17.08.2026 18:17:47),
предъявлен владельцем построчно, полностью. `.out.log` того же прогона — 0 байт: агент печатает
исключительно через `logging`, который направлен в поток ошибок; это признак нормальной работы
канала, а не потери лога (см. `reference/T-0-8_step7_handoff_executor_2026-08-17.md` §3).

```
INFO:lombard.agent.jwt_signer:JWT подписан: kid=lombard-agent-20260813 iss=https://erp-agent.lombard-ops.invalid aud=//iam.googleapis.com/projects/450925595005/locations/global/workloadIdentityPools/lombard-agent-federation-pool/providers/lombard-agent-jwt-provider sub=lombard-agent-erp01 iat=1786969037 exp=1786969637 (TTL=600s) — сам токен и приватный ключ в лог не идут
INFO:lombard.agent.jwt_signer:JWT записан в C:\LombardAgent\keys\signed_jwt.txt (путь публикуется, содержимое — никогда)
INFO:lombard.agent.run_daily:JWT обновлён перед прогоном (путь: C:\LombardAgent\keys\signed_jwt.txt)
INFO:lombard.agent.run_daily:значение учётки LOMBARD_RO прочитано из Secret Manager (firebird-readonly-creds, версия latest) — само значение в лог не идёт
INFO:lombard.agent.run_daily:подключение к Firebird: dsn=192.168.88.209/3057:D:\PawnShop_DOL\DB\DOL.FDB user=LOMBARD_RO charset=WIN1251
INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:19Z]: SELECT f.RDB$FIELD_NAME AS COLUMN_NAME, t.RDB$FIELD_TYPE AS FIELD_TYPE, t.RDB$FIELD_LENGTH AS FIELD_LENGTH, t.RDB$FIELD_SCALE AS FIELD_SCALE FROM RDB$RELATION_FIELDS f JOIN RDB$FIELDS t ON t.RDB$FIELD_NAME = f.RDB$FIELD_SOURCE WHERE f.RDB$RELATION_NAME = ? ORDER BY f.RDB$FIELD_POSITION
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
... (девять раз — по одному на каждую из девяти разрешённых таблиц, guard схемы читает метаданные перед данными)
INFO:lombard.agent.schema_guard:GUARD: отпечаток всех 9 таблиц совпал с эталоном
INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:19Z]: SELECT CONTRACT_ID, FILIAL_ID, CLIENT_ID, AGENT_ID, CONTRACT_NUM, CONTRACT_DATE, CONTRACT_STATE, CONTRACT_CLOSE, IS_ARCHIVE, MODIFY_DATE, NOTE, ID_NATIVE, ID_PREV_CONTRACT, BCODE, PLAN_CLOSE_DATE, DEPOSIT_SUM, SUBJECT_PRICE, DEPOSIT_TYPE, ID_DEPOSIT_PLACE, EXCHANGE_RATE, IS_USED_IN_STATISTICS, SUM_ROUND_PRECISION, ALLOW_SMS, NOTE_ON_CLOSE_CONTRACT, IS_NOT_CALC_FIRST_DAY FROM CONTRACTS
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 2509 строк из CONTRACTS
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACTS.ndjson (1529751 байт)
INFO:lombard.agent:выгрузка CONTRACTS: 2509 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACTS.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:21Z]: SELECT ID_TERM, CONTRACT_ID, PENALTY_DAYS, DEPOSIT_PERC, PENALTY_PERC, IS_PERC_STOP_W_PEN, EXCEED_DAYS, EXCEED_MONTHS, IS_PRIVILEGE_IN_EXCEED_DAYS, IS_PENAL_FROM_RET_SUM, MIN_PERC_DAYS, STORAGE_TYPE, STORAGE_VAL, IS_STORAGE_STOP_W_PEN, STORAGE_MIN_DAYS, USE_EXCHANGE, USE_EXCHANGE_IF_INCREASE, IS_PAY_PERC_ON_FUTURE, ACC_PAY_SCHEME, INSURE_TYPE, INSURE_VAL, IS_INSURE_STOP_W_PEN, INSURE_MIN_DAYS, START_MOMENT, ID_OP, TARIFF_NAME, ID_TARIF, IS_AUTO_ON_SALE, IS_CLOSE_VIA_SMS, IS_CLOSE_VIA_PHOTO FROM CONTRACTS_TERMS
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 2510 строк из CONTRACTS_TERMS
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACTS_TERMS.ndjson (1745151 байт)
INFO:lombard.agent:выгрузка CONTRACTS_TERMS: 2510 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACTS_TERMS.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:24Z]: SELECT ID, ID_CONTRACT, NAME, PRICE, DEPOSIT_SUM, ITEMS_COUNT, ID_NATIVE, NOTE, ID_BCODE_SUBJ, ID_FILES_PHOTO FROM SUBJECTS
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 2507 строк из SUBJECTS
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/SUBJECTS.ndjson (764645 байт)
INFO:lombard.agent:выгрузка SUBJECTS: 2507 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/SUBJECTS.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:27Z]: SELECT ID, ID_FIELD, ID_OBJ, FIELD_VALUE FROM CUSTOM_FIELDS_VALUES
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 12641 строк из CUSTOM_FIELDS_VALUES
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CUSTOM_FIELDS_VALUES.ndjson (873800 байт)
INFO:lombard.agent:выгрузка CUSTOM_FIELDS_VALUES: 12641 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CUSTOM_FIELDS_VALUES.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:32Z]: SELECT ID, ID_OBJ_TABLE, NAME, DEFAULT_VALUE, DOC_CODE, SORT_ORDER, ID_SUB_TYPE, FIELD_TYPE, CB_ITEMS, IS_REQURIED FROM DIR_CUSTOM_FIELDS
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 23 строк из DIR_CUSTOM_FIELDS
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/DIR_CUSTOM_FIELDS.ndjson (5304 байт)
INFO:lombard.agent:выгрузка DIR_CUSTOM_FIELDS: 23 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/DIR_CUSTOM_FIELDS.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:33Z]: SELECT ID, DBTABLE, TABLE_NAME, NAME_CATEG_DOCS, NAME_LOG_OBJ, SQL_GET_LOG_OBJ FROM TABLES_TABLE
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 17 строк из TABLES_TABLE
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/TABLES_TABLE.ndjson (2626 байт)
INFO:lombard.agent:выгрузка TABLES_TABLE: 17 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/TABLES_TABLE.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:35Z]: SELECT STATE_ID, CODE, SORT_ORDER FROM CONTRACT_STATES
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 6 строк из CONTRACT_STATES
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACT_STATES.ndjson (302 байт)
INFO:lombard.agent:выгрузка CONTRACT_STATES: 6 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACT_STATES.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:36Z]: SELECT ID, CODE FROM DEPOSIT_TYPES
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 7 строк из DEPOSIT_TYPES
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/DEPOSIT_TYPES.ndjson (182 байт)
INFO:lombard.agent:выгрузка DEPOSIT_TYPES: 7 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/DEPOSIT_TYPES.ndjson

INFO:lombard.agent.access_point:SQL к PawnShop [2026-08-17T12:17:37Z]: SELECT OP_ID, DEPOSIT_ID, OP_VID, OP_DATE, NON_CALC_DAYS, OP_SUM, OP_PERC_SUM_MAIN, OP_PERC_SUM_ADD, OP_STORAGE_SUM, OP_PENALTY_SUM, OP_INFO, ID_NATIVE, OP_REST_PERC_MAIN, OP_REST_STORAGE_MAIN, OP_REST_PENALTY_MAIN, OP_REST_BASE, OP_REST_PERC_ADD, OP_REST_STORAGE_ADD, OP_REST_PENALTY_ADD, PERC_ACC_DAYS, STOR_ACC_DAYS, PEN_ACC_DAYS, OP_INSURE_SUM, OP_REST_INSURE_MAIN, OP_REST_INSURE_ADD, INSURE_ACC_DAYS, CASH, CHANGE, REFIN_SUM_DBL, OP_REST_PERC_MAIN_DBL, IS_ONLINE, ID_ONLINE_FILIAL, ID_ONLINE_NATIVE, ID_AGENT FROM OPERATIONS
INFO:lombard.agent.access_point:режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
INFO:lombard.agent:прочитано 6554 строк из OPERATIONS
INFO:lombard.agent.gcs_upload:загрузка удалась с попытки 1/5: gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/OPERATIONS.ndjson (5137135 байт)
INFO:lombard.agent:выгрузка OPERATIONS: 6554 строк -> gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/OPERATIONS.ndjson
```

Перед каждым `SELECT` данных guard схемы выполняет тот же запрос к `RDB$RELATION_FIELDS`/`RDB$FIELDS`
для сверки отпечатка — строки повторяются девять раз (по числу таблиц) и в выдержке выше сведены
к одной с пометкой «девять раз»; полный текст без сокращений — в файле лога у владельца, объём
17177 байт совпадает с листингом каталога, предъявленным в передаче `reference/T-0-8_step7_handoff_executor_2026-08-17.md`.

**Прогон 18:02 (`run_daily_20260817_180215.err.log`, 8366 байт)** — более ранняя попытка того же дня,
меньшего объёма. Основным не является, в приёмку не идёт; в лог не предъявлялась и не разбиралась —
оснований для этого нет (шаг 7 закрывается прогоном 18:17).

## 3. Второй вход — листинг бакета выгрузки

Исполнено этой сессией, класс B, чтение, подтверждено карточкой (вопрос владельцу, 2026-08-17):

```
$ gcloud storage ls --recursive gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/:
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACTS.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACTS_TERMS.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CONTRACT_STATES.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/CUSTOM_FIELDS_VALUES.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/DEPOSIT_TYPES.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/DIR_CUSTOM_FIELDS.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/OPERATIONS.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/SUBJECTS.ndjson
gs://project-c451b48a-07ae-4de4-961-cfsource/agent/2026-08-17/TABLES_TABLE.ndjson
```

Девять объектов — по одному на каждую из девяти разрешённых таблиц (`briefs/T-0-5.md`). Имена
файлов совпадают дословно с именами таблиц из лога раздела 2; расхождений нет.

## 4. Сверка числа строк — лог против бакета

| Таблица | Строк (лог) | Объект в бакете | Объём (лог) |
|---|---|---|---|
| CONTRACTS | 2509 | `CONTRACTS.ndjson` | 1529751 байт |
| CONTRACTS_TERMS | 2510 | `CONTRACTS_TERMS.ndjson` | 1745151 байт |
| SUBJECTS | 2507 | `SUBJECTS.ndjson` | 764645 байт |
| CUSTOM_FIELDS_VALUES | 12641 | `CUSTOM_FIELDS_VALUES.ndjson` | 873800 байт |
| DIR_CUSTOM_FIELDS | 23 | `DIR_CUSTOM_FIELDS.ndjson` | 5304 байт |
| TABLES_TABLE | 17 | `TABLES_TABLE.ndjson` | 2626 байт |
| CONTRACT_STATES | 6 | `CONTRACT_STATES.ndjson` | 302 байт |
| DEPOSIT_TYPES | 7 | `DEPOSIT_TYPES.ndjson` | 182 байт |
| OPERATIONS | 6554 | `OPERATIONS.ndjson` | 5137135 байт |

Девять таблиц, девять объектов, девять числе строк — все из лога прогона, ни одно не досчитано и не
предположено. Расхождений между списком таблиц лога и листингом бакета нет.

## 5. Разбор — что подтверждает каждый пункт приёмки

- **Отпечаток схемы.** Строка `GUARD: отпечаток всех 9 таблиц совпал с эталоном` — положительный
  факт сверки с `connector/agent/schema_fingerprint.json`, а не отсутствие ошибки. Эталон был создан
  ранее (первый прогон на этой машине), сверка включена, как и предписано `10_GCP_INFRA_PLAYBOOK`.
- **Режим транзакции.** Строка `режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1`
  повторяется на каждый SQL-запрос (и метаданных, и данных) — запрос к `MON$TRANSACTIONS` подтверждает
  режим для каждой открытой транзакции отдельно, а не одной проверкой на весь прогон (`ADR-037`).
- **Точка доступа.** Каждый текст запроса напечатан ДО отправки (`Лог запроса печатается ДО отправки`,
  `10_GCP_INFRA_PLAYBOOK`) — предъявлено дословным совпадением текста в логе с колонками, которые
  ожидаются от guard-эталона по каждой таблице.
- **Поведение GCS.** Все девять загрузок ушли с первой попытки (`загрузка удалась с попытки 1/5`) —
  сеть не рвалась в этом прогоне; повтор и журнал не понадобились. Это НЕ проверка отказоустойчивости
  — она предмет отдельной пробы (playbook, раздел «Поведение при недоступности GCS»), здесь только
  факт нормального прохождения.
- **Секреты.** Ни токен, ни приватный ключ, ни пароль `LOMBARD_RO` в лог не напечатаны — предъявлено
  построчным чтением всего лога выше, ни одной строки с этими значениями нет.

## 6. Что этим артефактом НЕ закрыто

- **Отрицательный случай реального прогона** («попытка провести запрещённый оператор через точку
  доступа в реальном прогоне отбита») — закрыт отдельным артефактом
  `reference/T-0-8_step7_negative_probes_2026-08-17.md` (случай 1: `UPDATE` отбит на реальном
  подключении к Firebird ДО отправки на сервер, случай 2: просроченный JWT отбит платформой).
  Смешивать оба артефакта было бы дефектом нарезки — они предъявляют разные прогоны.
- **Шаг 8** (playbook, `INFRA_PATCH`, строка `07_GAPS`, session-блок) — предмет отдельной работы,
  следует за этим артефактом.
- **Третий факт условия переезда чтения БД в класс A** — оценка не выносится этим артефактом; первая
  половина (тест точки доступа) закрыта `reference/T-0-8_step7_negative_probes_2026-08-17.md`, вторая
  половина (реальное чтение через точку доступа со счётом строк) закрыта разделами 2 и 4 здесь.
  Итоговый ответ — в session-блоке отдельно, не здесь.
