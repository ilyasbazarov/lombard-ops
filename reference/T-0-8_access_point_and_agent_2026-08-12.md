T-0-8_access_point_and_agent_2026-08-12.md

# T-0-8 · Шаги 2–4 (класс A, стол): точка доступа с белым списком, её тест, агент

Артефакт отдельного предмета от `reference/T-0-8_agent_channel_measurement_2026-08-12.md` и
`reference/T-0-8_channel_remeasurement_2026-08-12.md` (оба — шаг 1, связность). Здесь —
шаги 2–4 брифа `briefs/T-0-8.md` + ПОПРАВКА 1 (`ADR-048`): предъявлены логом на нашей
стороне, к базе клиента и к облаку не подключаясь (шаги 5–7 остаются классом B и не
исполнены этой сессией).

**Коммит на входе сессии:** `bdbc1a7e590dccab33178f377e31a2dc246a38c1`.
**Окружение замера:** локальная машина Ilyas (не сервер клиента, не сервер прода) —
все проверки на этой странице читают только код репозитория и фиктивные объекты, к
базе PawnShop и к GCP не обращаются нигде.

## 1. Единственная точка доступа — `connector/agent/access_point.py`

Требование шага 2: разбирает оператор, а не ищет подстроку (`ADR-048`); пропускает
только `SELECT`/`WITH … SELECT`; `SELECT *` запрещён; таблица — из белого списка
девяти (`briefs/T-0-5.md`) плюс `RDB$*`/`MON$*`; печатает запрос в лог до отправки;
транзакция — только на чтение, режим подтверждается положительным фактом
(`MON$READ_ONLY`, `ADR-037`), а не отсутствием ошибки.

### 1.1 Разбор оператора — штатным механизмом (`ADR-048`), не сравнением строк

Модуль использует `sqlparse` — стандартный токенизатор/парсер SQL для Python — и
берёт тип оператора из `Statement.get_type()` (грамматический разбор), не ищет слово
в тексте. Проверено прямо интерпретатором на дюжине конструкций до включения в тест:

```
$ python3 -c "
import sqlparse
tests = ['SELECT ID FROM T', 'WITH T AS (SELECT ID FROM X) SELECT * FROM T',
          'UPDATE T SET ID=1', '\n\n  uPdAtE T SET ID=1', 'GRANT SELECT ON T TO PUBLIC',
          'EXECUTE BLOCK AS BEGIN END']
for t in tests:
    print(repr(t[:30]), '->', sqlparse.parse(t)[0].get_type())
"
'SELECT ID FROM T' -> SELECT
'WITH T AS (SELECT ID FROM X) ' -> SELECT
'UPDATE T SET ID=1' -> UPDATE
'\n\n  uPdAtE T SET ID=1' -> UPDATE
'GRANT SELECT ON T TO PUBLIC' -> UNKNOWN
'EXECUTE BLOCK AS BEGIN END' -> UNKNOWN
```

Белый список пропускает буквально `'SELECT'` — `UNKNOWN` (GRANT, EXECUTE BLOCK, ...)
отбивается тем же путём, что и любой другой тип, без отдельной ветки под каждый
запрещённый глагол.

### 1.2 `validate_query` — 17 контрастных случаев, оба исхода каждой проверки

```
$ python3 -c "... (полный код — connector/agent/test_access_point.py и тело сессии) ..."
OK   expected=True   sql='SELECT ID, NAME FROM CONTRACTS'
OK   expected=False  sql='SELECT * FROM CONTRACTS'
OK   expected=False  sql='UPDATE CONTRACTS SET ID = ID WHERE 1=0'
OK   expected=False  sql='DELETE FROM CONTRACTS'
OK   expected=False  sql='DROP TABLE CONTRACTS'
OK   expected=False  sql='GRANT SELECT ON CONTRACTS TO PUBLIC'
OK   expected=False  sql='EXECUTE BLOCK AS BEGIN END'
OK   expected=False  sql='INSERT INTO CONTRACTS (ID) VALUES (1)'
OK   expected=True   sql='-- UPDATE fake\nSELECT ID FROM CONTRACTS'
OK   expected=True   sql="SELECT 'contains UPDATE word' AS X FROM CONTRACTS"
OK   expected=False  sql='\n\n  uPdAtE CONTRACTS SET ID=1'
OK   expected=True   sql='WITH T AS (SELECT ID FROM CONTRACTS) SELECT ID FROM T'
OK   expected=False  sql='SELECT ID FROM SOME_OTHER_TABLE'
OK   expected=True   sql='SELECT RDB$FIELD_NAME FROM RDB$RELATION_FIELDS'
OK   expected=True   sql='SELECT MON$TRANSACTION_ID FROM MON$TRANSACTIONS'
OK   expected=False  sql='SELECT ID FROM CONTRACTS; DROP TABLE CONTRACTS'
OK   expected=True   sql='SELECT ID, COUNT(*) FROM CONTRACTS GROUP BY ID'
FAILS: 0
```

`COUNT(*)` внутри агрегатной функции отличается от голого `SELECT *` разбором дерева
токенов (обход пропускает содержимое `Function(...)`), а не текстовым исключением —
иначе легитимный `SELECT ID, COUNT(*) FROM CONTRACTS GROUP BY ID` ложно отбивался бы.

## 2. Тест точки доступа — `connector/agent/test_access_point.py` (шаг 3)

К базе клиента не подключается: `FakeConnection`/`FakeTransaction`/`FakeCursor`
подменяют `fdb`-объекты полностью, `access_point()` вызывается с
`transaction_factory=_factory`, указывающим на фиктивную транзакцию. Обе стороны
каждой проверки (`ADR-033`) — в одном тесте:

```
$ python3 -m connector.agent.test_access_point
[пройдено]  1a: разрешённый SELECT по разрешённой таблице — проходит и возвращает строки
[пройдено]  1b: разрешённый SELECT по RDB$ (метаданные guard схемы) — проходит
[пройдено]  2a: UPDATE — отбивается исключением ДО обращения к соединению
[пройдено]  2b: INSERT — отбивается исключением
[пройдено]  2c: DELETE — отбивается исключением
[пройдено]  2d: DROP — отбивается исключением
[пройдено]  2e: GRANT — отбивается исключением
[пройдено]  2f: EXECUTE BLOCK — отбивается исключением
[пройдено]  3: SELECT с запрещённым словом внутри КОММЕНТАРИЯ — проходит (доказывает разбор оператора, а не поиск подстроки, ADR-048)
[пройдено]  3-БИС: SELECT с запрещённым словом внутри СТРОКОВОГО ЛИТЕРАЛА — проходит
[пройдено]  4: UPDATE, замаскированный переносами строк и регистром, — отбивается
[пройдено]  5: обращение к таблице вне девяти разрешённых — отбивается
[пройдено]  5-БИС: разрешённая таблица среди девяти, для контраста с проверкой 5 (положительный контроль различимости — ADR-033)
[пройдено]  6: попытка работы при режиме транзакции НЕ read-only — отбивается (положительный факт MON$READ_ONLY, а не отсутствие ошибки, ADR-037)
[пройдено]  6-БИС: та же таблица и запрос при режиме read-only=1 — проходит (положительный контроль для проверки 6, ADR-033)

всего проверок: 15; провалено 0
```

(15 проверок в реестре `_checks`, все напечатаны строкой `[пройдено]` выше — счёт
совпадает построчно, расхождения нет.)

Проверка 2a-2f отдельно доказывает: `conn.trans_calls == 0` после отказа — запрещённый
оператор не доходит до соединения вообще, что и требует шаг 2 брифа («отбивает
исключением ДО отправки на сервер»).

## 3. Единственный путь SQL к базе — предъявлено поиском (критерий приёмки)

```
$ grep -rn "fdb\.\|\.execute(\|\.cursor(" --include="*.py" . \
    | grep -v "connector/agent/access_point.py" \
    | grep -v "connector/agent/test_access_point.py"
(пусто)

$ grep -rln "import fdb" --include="*.py" .
./connector/agent/access_point.py
```

`fdb` импортируется РОВНО в одном файле проекта; больше нигде в дереве нет прямого
обращения к `.execute()`/`.cursor()` вне `access_point.py` и его теста. Это и есть
предъявление «весь SQL проекта к PawnShop идёт через одну функцию».

## 4. Агент — guard схемы, чтение, выгрузка (шаг 4)

`connector/agent/schema_guard.py` + `connector/agent/agent.py` +
`connector/agent/gcs_upload.py`. Подключение к БД и к GCS подменены фиктивными
объектами того же вида, что в шаге 3 — к серверу клиента и к облаку код не обращался.

### 4.1 Первый прогон создаёт отпечаток; второй проходит молча; расхождение — стоп

```
GUARD: эталон отпечатка отсутствует (.../fp.json) — ПЕРВЫЙ ПРОГОН создаёт его.
Сверка схемы включается со следующего прогона, не с этого.
first run results: {'CONTRACTS': 'gs://fake-bucket/agent/2026-08-12/CONTRACTS.ndjson', ...
  (все девять таблиц: CONTRACTS, CONTRACTS_TERMS, SUBJECTS, CUSTOM_FIELDS_VALUES,
   DIR_CUSTOM_FIELDS, TABLES_TABLE, CONTRACT_STATES, DEPOSIT_TYPES, OPERATIONS)
fingerprint file exists: True
store keys: [9 объектов agent/2026-08-12/<TABLE>.ndjson]
agent/2026-08-12/CONTRACTS.ndjson -> b'{"ID": 1, "NAME": "A"}\n{"ID": 2, "NAME": "B"}\n'
  ... (по одному NDJSON-объекту на таблицу, содержимое построено из fake-строк)

second run results: {'CONTRACTS': 'gs://fake-bucket/agent/2026-08-13/CONTRACTS.ndjson', ...}
  (эталон уже существовал — сверка прошла молча, guard_check не создавал файл заново)
```

### 4.2 Расхождение отпечатка — стоп для ВСЕХ девяти таблиц, а не только для изменившейся

Третий прогон: колонка `NEW_COL` добавлена в фиктивную схему `CONTRACTS`.

```
GUARD MISMATCH CONTRACTS: эталон=[['ID', 8, 4, 0], ['NAME', 14, 100, 0]]
  ИЗМЕРЕНО=[['ID', 8, 4, 0], ['NAME', 14, 100, 0], ['NEW_COL', 8, 4, 0]]
GUARD ОСТАНОВИЛ ПРОГОН: расхождение отпечатка схемы — чтение НЕ выполняется
  ни для одной таблицы (00 §3-БИС(c): стоп и алерт, не искажение)

third run stopped as expected: SchemaGuardMismatch расхождение отпечатка схемы на
  1 таблиц(е): ['CONTRACTS'] — чтение остановлено, эталон НЕ обновлён
store after third run (must be empty): {}
```

`store` (фиктивный GCS) пуст после третьего прогона — ни одна из девяти таблиц не
выгружена, включая восемь, чей отпечаток не менялся: это и есть «стоп, не искажение».

### 4.3 Поведение при недоступности GCS: повтор с задержкой → предел попыток → локальный журнал, без потери

```
$ python3 -c "... upload_bytes с always_fail_client ..."
попытка загрузки 1/3 не удалась (agent/2026-08-12/CONTRACTS.ndjson): сеть недоступна (симуляция недоступности GCS)
  (симулированная задержка перед повтором: 2.000s, номер 1)
попытка загрузки 2/3 не удалась (agent/2026-08-12/CONTRACTS.ndjson): сеть недоступна (симуляция недоступности GCS)
  (симулированная задержка перед повтором: 4.000s, номер 2)
попытка загрузки 3/3 не удалась (agent/2026-08-12/CONTRACTS.ndjson): сеть недоступна (симуляция недоступности GCS)
все 3 попыток загрузки исчерпаны для agent/2026-08-12/CONTRACTS.ndjson (последняя ошибка: сеть недоступна (симуляция недоступности GCS));
  объект сохранён БЕЗ ПОТЕРИ в локальный журнал: /var/folders/.../agent__2026-08-12__CONTRACTS.ndjson
ОЖИДАЕМЫЙ ОТКАЗ: загрузка agent/2026-08-12/CONTRACTS.ndjson не удалась за 3 попыток; объект сохранён в локальный журнал: ...
журнал-файл существует: True
содержимое журнала не потеряно: b'{"ID": 1}\n'
```

Задержка растёт экспоненциально (`base_delay_seconds * 2**попытка`); после исчерпания
попыток объект пишется в `journal_dir` побайтово тем же содержимым, что должно было
уйти в GCS, и функция бросает `UploadFailedPersisted` — вызывающий код узнаёт об
отказе явно. `gcs_upload.replay_journal()` доисполняет хвост при восстановлении связи
(не-идемпотентные операции, `05 §I`): читает журнал, повторяет загрузку, удаляет файл
из журнала только при успехе.

### 4.4 Список колонок — из измеренного отпечатка, не придуман

`agent.extract_table()` строит `SELECT <явный список>` из `column_names(fingerprint)`
— тех самых имён колонок, что дал запрос к `RDB$RELATION_FIELDS`/`RDB$FIELDS` этой же
сессией. Схема БД PawnShop нигде не угадана руками (`00 §Anti-improvisation`): агент
не содержит ни одного захардкоженного имени колонки, только имена таблиц (белый
список `briefs/T-0-5.md`) и SQL текста самого guard-запроса (тоже явным списком
колонок системной таблицы, без `SELECT *`).

## 5. Что НЕ сделано этой сессией (класс B, отдельные карточки)

- Связность до `secretmanager.googleapis.com` (остаток `ADR-048`) — не измерена,
  требует прогона на сервере ERP; карточка подтверждения — в session-блоке.
- Ключ сервисного аккаунта и запись пароля в Secret Manager (шаг 5) — не исполнены.
- Установка агента службой на сервер (шаг 6) — не исполнена.
- Прогон и предъявление на реальных данных (шаг 7) — не исполнен.

Ни разу за сессию не открывалось соединение к серверу ERP и не делалось ни одного
обращения к облаку клиента — весь код этой части написан и проверен на фиктивных
объектах, как и требует класс A мандата.
