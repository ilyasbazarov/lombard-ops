# T-0-10 · Эталон отпечатка used-таблиц в `connector/mapping.json` — лог сессии

**Дата:** 2026-08-18 · **Класс:** A · **Вход:** `/Users/ilyasbazarov/Downloads/meta_out.txt`
(вне репозитория, не коммитится, `ADR-009`) · **Коммит на входе:** `ccffb3fdaf363df7d93e9531b646aaebfb419b75`

## 1. Лог парсера `meta_out.txt` (шаг 1 брифа)

Парсер — регекс по структуре токенов строки данных секции 2 (`TABLE POS COLUMN FTYPE
FSUBTYPE FLEN FSCALE NOTNULL DESCR...`), не по фиксированной ширине `====`-разделителя:
разделитель в файле короче (289 символов), чем реальные данные (COLUMN_DESCR до ~1200
символов) — колонки по позициям `====`-строки съезжали, регекс-подход этого не делает.
Строка данных распознаётся по совпадению с шаблоном И принадлежности первого токена
множеству из 108 имён таблиц секции 1; иначе — продолжение `COLUMN_DESCR` предыдущей
распознанной строки (конкатенация через пробел).

Вывод прогона (дословно):
```
sec1 header pages: 6, sec2 header pages: 51
sec1 tables parsed: 108
sec2 data rows parsed: 1018
sec2 continuation lines glued: 109
sum records+continuations: 1127
sec2 nonempty lines total (excl headers/seps/blank): 1127
saved parsed_meta.json
```
`1018 + 109 = 1127` совпадает со счётом непустых строк секции 2 (`assert` в скрипте
прошёл, иначе скрипт падает).

## 2. `schema_fingerprint` по девяти used-таблицам (шаг 2 брифа)

Список ключей `mapping.json["schema_fingerprint"]` против `access_point.ALLOWED_TABLES`:
```
schema_fingerprint tables: ['CONTRACTS', 'CONTRACTS_TERMS', 'CONTRACT_STATES', 'CUSTOM_FIELDS_VALUES', 'DEPOSIT_TYPES', 'DIR_CUSTOM_FIELDS', 'OPERATIONS', 'SUBJECTS', 'TABLES_TABLE']
ALLOWED_TABLES: ['CONTRACTS', 'CONTRACTS_TERMS', 'CONTRACT_STATES', 'CUSTOM_FIELDS_VALUES', 'DEPOSIT_TYPES', 'DIR_CUSTOM_FIELDS', 'OPERATIONS', 'SUBJECTS', 'TABLES_TABLE']
EQUAL: True
```
Число колонок отпечатка по таблице (`POS`-порядок сохранён):
```
CONTRACTS 25
CONTRACTS_TERMS 30
SUBJECTS 10
CUSTOM_FIELDS_VALUES 4
DIR_CUSTOM_FIELDS 10
TABLES_TABLE 6
CONTRACT_STATES 3
DEPOSIT_TYPES 2
OPERATIONS 34
```
`table_count: 9  column_count: 124` (сумма выше) — записано в `mapping.json` метаданными.

Пересечение с §3 `02_DATA_CONTRACTS.md`: шесть таблиц названы там прямо в колонке
«Таблица.колонка Firebird» (`CONTRACTS`, `CONTRACTS_TERMS`, `SUBJECTS`,
`CUSTOM_FIELDS_VALUES`, `DIR_CUSTOM_FIELDS`, `OPERATIONS`); ещё три (`TABLES_TABLE`,
`CONTRACT_STATES`, `DEPOSIT_TYPES`) входят в used-список белым списком `access_point.py`
(источник — `briefs/T-0-5.md` §«Список таблиц», тот же первоисточник, что называет бриф
`T-0-10`), но не фигурируют дословно в строках §3 — это справочные/статусные таблицы, не
предмет field-level маппинга. Полный used-список (девять) — `ALLOWED_TABLES`, с ним
`mapping.json` совпадает построчно (см. выше).

## 3. Тест guard'а на mock-соединении (шаг 5 брифа, `ADR-080` п.3) — `connector/agent/test_schema_guard.py`

Команда: `python3 -m connector.agent.test_schema_guard` (с `logging.basicConfig(level=INFO)`
для предъявления обоих логов guard'а). Вывод дословно:

```
INFO lombard.agent.access_point: SQL к PawnShop [2026-08-18T14:56:11Z]: SELECT f.RDB$FIELD_NAME AS COLUMN_NAME, t.RDB$FIELD_TYPE AS FIELD_TYPE, t.RDB$FIELD_LENGTH AS FIELD_LENGTH, t.RDB$FIELD_SCALE AS FIELD_SCALE FROM RDB$RELATION_FIELDS f JOIN RDB$FIELDS t ON t.RDB$FIELD_NAME = f.RDB$FIELD_SOURCE WHERE f.RDB$RELATION_NAME = ? ORDER BY f.RDB$FIELD_POSITION
INFO lombard.agent.access_point: режим транзакции подтверждён положительным фактом: MON$READ_ONLY=1
... (по одному разу на каждую из девяти таблиц) ...
INFO lombard.agent.schema_guard: GUARD: отпечаток всех 9 таблиц совпал с эталоном
[пройдено]  (а) untouched: измеренное совпадает с mapping.json — guard_check проходит молча
INFO lombard.agent.access_point: SQL к PawnShop [2026-08-18T14:56:11Z]: SELECT f.RDB$FIELD_NAME AS COLUMN_NAME, ...
... (по одному разу на каждую из девяти таблиц) ...
ERROR lombard.agent.schema_guard: GUARD MISMATCH CONTRACTS: эталон=[['CONTRACT_ID', 8, 4, 0], ...] ИЗМЕРЕНО=[['CONTRACT_ID', 9, 4, 0], ...]
[пройдено]  (б) искажённый: один FIELD_TYPE одной колонки одной таблицы подменён — SchemaGuardMismatch, ни одна таблица не считается прочитанной

всего проверок: 2; провалено 0
```

Случай (а) — `logger.info("GUARD: отпечаток всех %d таблиц совпал с эталоном", 9)`, исключения
нет, `guard_check` вернул измеренные данные, тест сверил их с `mapping.json["schema_fingerprint"]`
по всем девяти таблицам целиком (не только `CONTRACTS`).

Случай (б) — `FIELD_TYPE` колонки `CONTRACT_ID` таблицы `CONTRACTS` подменён `8 → 9` в
измерении (mock); `logger.error("GUARD MISMATCH CONTRACTS: эталон=... ИЗМЕРЕНО=...")`,
`SchemaGuardMismatch` брошено, `guard_check` не вернул результат вовсе (исключение
перехвачено тестом, а не проглочено) — ни одна из девяти таблиц не считается прочитанной,
как того требует сама логика `guard_check` (расхождение стопит весь снимок).

## 4. Обращения к БД PawnShop

Ни одного: `test_schema_guard.py` подключение и транзакцию подменяет
(`FakeConnection`/`FakeTransaction`/`FakeCursor`, тот же приём, что
`connector/agent/test_access_point.py`), `transaction_factory` пробрасывается явно.
Единственный `import fdb` в дереве — локальный внутри `access_point._read_only_transaction`,
не исполняется в тестовом пути (подмена происходит до него).

## 5. `meta_out.txt` в диффе

Не встречается: файл читался с диска вне репозитория, в `git add`/коммит не входил ни разу
(команды парсера писали временные файлы в scratchpad-директорию сессии, не в дерево репозитория).
