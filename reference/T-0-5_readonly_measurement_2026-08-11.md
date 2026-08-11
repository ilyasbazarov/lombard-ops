# T-0-5 — замер read-only пользователя LOMBARD_RO

**Дата:** 2026-08-11 · **Задача:** T-0-5 · **Коммит на входе:** de9de31 (`git rev-parse HEAD`)

Модель исполнения: команды на сервере запускал Ilyas по RDP, логи вставлялись в чат целиком.
Ниже — логи как предъявлены, без пересказа. Пароли, полный список учётных записей сервера и
полный список таблиц схемы вендора в этот файл не попадают (`ADR-001`, `ADR-009`).

---

## Шаг 1-БИС — права `LOMBARD_RO` на входе (RDB$USER_PRIVILEGES)

Запрос под SYSDBA: `SELECT RDB$USER, RDB$RELATION_NAME, RDB$PRIVILEGE, RDB$GRANT_OPTION,
RDB$GRANTOR FROM RDB$USER_PRIVILEGES WHERE RDB$USER = 'LOMBARD_RO' ORDER BY RDB$RELATION_NAME,
RDB$PRIVILEGE;`

Результат — ровно 9 строк, право `S` (SELECT) на каждую, `RDB$GRANT_OPTION = 0`, `RDB$GRANTOR =
SYSDBA`:

```
CONTRACTS               S
CONTRACTS_TERMS         S
CONTRACT_STATES         S
CUSTOM_FIELDS_VALUES    S
DEPOSIT_TYPES           S
DIR_CUSTOM_FIELDS       S
OPERATIONS              S
SUBJECTS                S
TABLES_TABLE            S
```

**Вердикт шага 2 (ветка):** (б) — права `LOMBARD_RO` есть и совпадают с девятью таблицами брифа
один в один, лишнего и недостающего нет.

Отклонение от процедуры: предписанная брифом проверка байтов файла запроса (`Format-Hex -Count`)
не сработала (в установленной версии Windows PowerShell нет параметра `-Count`). Отсутствие BOM
подтверждено косвенно — `isql` разобрал файл и вернул корректные строки без ошибки `Token
unknown`, которая была бы при BOM.

## Шаг 3 (сброс пароля) — ЗАМЕНЁН проверкой подключения, сброс не потребовался

Владелец заявил, что помнит пароль `LOMBARD_RO`. Заявление проверено замером, не принято на
веру: подключение под `LOMBARD_RO` с паролем, который держит владелец, прошло успешно
(`SELECT 1 FROM RDB$DATABASE` вернул `1`). Пароль рабочий — административный сброс не
выполнялся, учётка не тронута.

## Шаг 4 — прогон `scripts/grant_ro.sql` для фиксации идемпотентности

9 команд `GRANT SELECT ... TO LOMBARD_RO` под SYSDBA. Вывод пустой, `$LASTEXITCODE = 0` —
подтверждено отдельной командой после прогона. Ошибок нет.

## Шаг 6-а — COUNT(*) по девяти таблицам (под LOMBARD_RO)

```
CNT_CONTRACTS               2490
CNT_CONTRACTS_TERMS         2491
CNT_SUBJECTS                2488
CNT_CUSTOM_FIELDS_VALUES   12470
CNT_DIR_CUSTOM_FIELDS         23
CNT_TABLES_TABLE              17
CNT_CONTRACT_STATES            6
CNT_DEPOSIT_TYPES              7
CNT_OPERATIONS               6486
```

Все девять — числа, без ошибок. Пройдено.

## Шаг 6-б — чтение RDB$-метаданных (под LOMBARD_RO)

`SELECT FIRST 5 RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 1 ORDER BY
RDB$RELATION_NAME;` вернул 5 системных имён (`MON$ATTACHMENTS`, `MON$CALL_STACK`,
`MON$CONTEXT_VARIABLES`, `MON$DATABASE`, `MON$IO_STATS`). Чтение `RDB$` работает — guard схемы
(`ADR-004`) не заблокирован. Пройдено.

Побочный дискавери-запрос (`RDB$SYSTEM_FLAG = 0`, до 20 имён пользовательских таблиц) выполнен
для нужд шага 6-в — сам список таблиц вендора в этот артефакт не переносится (`ADR-009`).

## Шаг 6-в — чтение НЕ выданной таблицы (под LOMBARD_RO) — ПРОВАЛЕН

`SELECT COUNT(*) FROM <таблица вне списка девяти>;` вернул число (`2693`), а не ошибку прав.
**Ожидался отказ, получен успех — лишние права, стоп по правилу брифа.**

## Диагностика причины — PUBLIC

`SELECT RDB$USER, RDB$PRIVILEGE, RDB$GRANT_OPTION, RDB$GRANTOR FROM RDB$USER_PRIVILEGES WHERE
RDB$RELATION_NAME = '<та же таблица>';` показал, что права на неё выданы не `LOMBARD_RO`, а
псевдо-пользователю `PUBLIC` — `S`, `I`, `U`, `D`, `R` (полный CRUD), грантор `SYSDBA`.

`SELECT COUNT(*) FROM RDB$USER_PRIVILEGES WHERE RDB$USER = 'PUBLIC' AND RDB$PRIVILEGE = 'S' AND
RDB$OBJECT_TYPE = 0;` вернул `107` — `PUBLIC` имеет `SELECT` минимум на 107 таблиц базы. Это
политика вендора на уровне всей БД, не создана этой задачей.

Проверено прицельно и по девяти нашим таблицам: `SELECT RDB$USER, RDB$RELATION_NAME,
RDB$PRIVILEGE FROM RDB$USER_PRIVILEGES WHERE RDB$USER = 'PUBLIC' AND RDB$RELATION_NAME IN
(<девять имён>) ORDER BY RDB$RELATION_NAME, RDB$PRIVILEGE;` — на КАЖДОЙ из девяти таблиц у
`PUBLIC` есть все пять прав `D/I/R/S/U`.

## Шаг 6-г — попытка записи (под LOMBARD_RO) — ПРОВАЛЕН, красная линия под угрозой

`UPDATE DEPOSIT_TYPES SET ID = ID WHERE 1 = 0;` (колонка `ID` подтверждена живым запросом к
`RDB$RELATION_FIELDS`, не угадана) — **прошёл без ошибки**, вывод пустой, `$LASTEXITCODE = 0`.
Данные не изменены (`WHERE 1 = 0` гарантирует ноль задетых строк), но право на запись
подтверждено фактом отсутствия ошибки.

**Обратный запрос, доказывающий исправность инструмента:** `UPDATE DEPOSIT_TYPES SET
NO_SUCH_COLUMN_XYZ = 1 WHERE 1 = 0;` под той же учёткой вернул `Statement failed, SQLSTATE =
42S22 ... Column unknown ... NO_SUCH_COLUMN_XYZ`, код возврата `1`. Инструмент печатает ошибки,
когда они есть — тишина на реальном `UPDATE` не является гэпом наблюдения, это факт.

**Вывод: `LOMBARD_RO` в текущем состоянии базы способен выполнять запись на все девять нужных
таблиц (и минимум на ещё одну проверенную вне списка) — из-за прав `PUBLIC`, а не из-за
`grant_ro.sql`.** Красная линия `00 §4` («к БД PawnShop — только чтение») не обеспечена на
уровне СУБД для этой учётки.

## Шаг 6-д — особенность 8-символьного пароля (под LOMBARD_RO)

Подключение с паролем, совпадающим с рабочим по первым 8 символам и отличающимся дальше:

```
Statement failed, SQLSTATE = 28000
Your user name and password are not defined. Ask your database administrator to set up a
Firebird login.
```

Вход отбит. **Особенность НЕ подтверждена** — полный пароль (не только первые 8 символов) значим
для аутентификации в этой инсталляции.

## Путь к базе (для INFRA_PATCH)

Строка подключения, использованная во всех командах: `localhost/3057:D:\PawnShop_DOL\DB\DOL.FDB`.
Путь к файлу `.fdb`: `D:\PawnShop_DOL\DB\DOL.FDB` — ранее в `11_INFRA_FACTS.md` стоял `⏳`, теперь
измерен.

## Итог

Приёмка брифа `T-0-5` **не закрыта**. Пройдено: 1-БИС, 2, 3(заменён), 4, 6-а, 6-б, 6-д(отрицательный
исход зафиксирован как валидный результат). **Провалено: 6-в, 6-г** — обнаружены лишние права,
источник — гранты `PUBLIC` на уровне всей БД, выданные вендором (`SYSDBA`) до этой задачи и вне
её мандата. Отзыв прав `PUBLIC` — решение архитектурного/владельческого уровня (масштаб всей
схемы, риск для самого приложения PawnShop), не класс A и не в мандате исполнителя. `CONTEXT GAP`
передан архитектору.
