# T-0-5 — замер шагов 6-е-БИС и 6-ж (режим транзакции и агрегаты прав PUBLIC), ПОПРАВКА 2 / ADR-036

**Дата:** 2026-08-11 · **Задача:** T-0-5 · **Коммит на входе:** 00d7234 (`git rev-parse HEAD`)

Модель исполнения: команду на сервере запускал Ilyas по RDP, логи вставлялись в чат целиком.
Ниже — логи как предъявлены, без пересказа. Пароли в этот файл не попадают (`ADR-001`).

Оба лога уже разобраны и засчитаны решением `ADR-036`: команды брифа несли дефект вызова
(в 6-е-БИС файл запроса не подавался вовсе, в 6-ж отсутствовала строка подключения), и обе были
исправлены на месте владельцем ДО того, как архитектор внёс каноническую правку в сам бриф.
Ремонт вызова проверяемого утверждения не менял: SQL, учётная запись, режим транзакции и предикаты
остались теми же, поэтому логи действительны. Ниже приведены обе формы команды для каждого шага —
«как написано в брифе» (каноническая, после правки `ADR-036`) и «как было запущено фактически».

---

## Шаг 6-е-БИС — как движок называет режим текущей транзакции (под `LOMBARD_RO`)

**Команда, как написано в свежем брифе (каноническая, после правки ADR-036):**

```powershell
$fbRoot = 'C:\Program Files (x86)\Firebird-2.5-PawnShop\'
$isql   = Join-Path $fbRoot 'bin\isql.exe'
if (-not (Test-Path $isql)) { Write-Host "CONTEXT GAP: не найден isql по пути $isql"; return }

$work = 'C:\Temp\lombard'
New-Item -ItemType Directory -Force -Path $work | Out-Null
$q   = Join-Path $work 'step6ebis.sql'
$out = Join-Path $work 'step6ebis_out.txt'
Remove-Item -Path $out -Force -ErrorAction SilentlyContinue

$sql = @'
SET LIST ON;
COMMIT;
SELECT MON$TRANSACTION_ID AS TX_RW, MON$READ_ONLY AS RO_FLAG_RW, MON$ISOLATION_MODE AS ISO_RW
  FROM MON$TRANSACTIONS WHERE MON$TRANSACTION_ID = CURRENT_TRANSACTION;
COMMIT;
SET TRANSACTION READ ONLY;
SELECT MON$TRANSACTION_ID AS TX_RO, MON$READ_ONLY AS RO_FLAG_RO, MON$ISOLATION_MODE AS ISO_RO
  FROM MON$TRANSACTIONS WHERE MON$TRANSACTION_ID = CURRENT_TRANSACTION;
COMMIT;
'@
[System.IO.File]::WriteAllText($q, $sql, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "первые байты файла запроса:" (([System.IO.File]::ReadAllBytes($q))[0..7] -join ' ')

$ro = Read-Host 'Учётная запись LOMBARD_RO — введите её пароль'
& $isql -user LOMBARD_RO -pas $ro -e -m -i $q -o $out "localhost/3057:D:\PawnShop_DOL\DB\DOL.FDB"
Write-Host "код возврата isql: $LASTEXITCODE"
Get-Content -Path $out -Encoding UTF8
```

**Команда, как была запущена фактически (до правки брифа, порядок аргументов починен на месте):**

```powershell
$ro = Read-Host 'Учётная запись LOMBARD_RO — введите её пароль'
& $isql -user LOMBARD_RO -pas $ro -e -m -i $q -o $out "localhost/3057:D:\PawnShop_DOL\DB\DOL.FDB"
Write-Host "код возврата isql: $LASTEXITCODE"
Get-Content -Path $out -Encoding UTF8
```

**Что изменилось между брифовой формой шага и фактическим запуском.** В брифе (до правки
`ADR-036`) вызов `isql` для этого шага не подавал файл запроса `$q` в аргументе `-i` вовсе.
Фактически запущенная команда несёт и `-i $q`, и строку подключения `-o $out
"localhost/3057:D:\PawnShop_DOL\DB\DOL.FDB"` — то есть исполнена сразу в исправленном виде. SQL,
учётная запись, режим транзакции и предикаты не менялись.

**Лог (код возврата isql: 0):**

```
SET LIST ON;
COMMIT;
SELECT MON$TRANSACTION_ID AS TX_RW, MON$READ_ONLY AS RO_FLAG_RW, MON$ISOLATION_MODE AS ISO_RW
  FROM MON$TRANSACTIONS WHERE MON$TRANSACTION_ID = CURRENT_TRANSACTION;

TX_RW                           20900841
RO_FLAG_RW                      0
ISO_RW                          1


COMMIT;
SET TRANSACTION READ ONLY;
SELECT MON$TRANSACTION_ID AS TX_RO, MON$READ_ONLY AS RO_FLAG_RO, MON$ISOLATION_MODE AS ISO_RO
  FROM MON$TRANSACTIONS WHERE MON$TRANSACTION_ID = CURRENT_TRANSACTION;

TX_RO                           20900843
RO_FLAG_RO                      1
ISO_RO                          1


COMMIT;
```

**Исход (по критерию брифа).** `RO_FLAG_RW` (`0`) и `RO_FLAG_RO` (`1`) — разные значения; номера
транзакций (`20900841` и `20900843`) тоже разные, значит второй прогон идёт в новой транзакции.
«Признаки различаются» — режим транзакции переключается. Шаг пройден. Факт, который это снимает:
`SET TRANSACTION READ ONLY` на базе клиента режим переключает — движок объявляет транзакцию
только на чтение. Вопрос уровня отказа (отказ на уровне оператора против отказа на уровне записи)
остаётся у `T-0-17`, этим шагом не закрывается.

---

## Шаг 6-ж — агрегаты прав PUBLIC и число получателей прав (под `LOMBARD_RO`, только чтение)

**Команда, как написано в свежем брифе (каноническая, после правки ADR-036):**

```powershell
$fbRoot = 'C:\Program Files (x86)\Firebird-2.5-PawnShop\'
$isql   = Join-Path $fbRoot 'bin\isql.exe'
if (-not (Test-Path $isql)) { Write-Host "CONTEXT GAP: не найден isql по пути $isql"; return }

$work = 'C:\Temp\lombard'
New-Item -ItemType Directory -Force -Path $work | Out-Null
$q   = Join-Path $work 'step6zh.sql'
$out = Join-Path $work 'step6zh_out.txt'

$sql = @'
SET LIST ON;
SELECT RDB$PRIVILEGE AS PRIV, COUNT(*) AS CNT_OBJECTS
  FROM RDB$USER_PRIVILEGES
 WHERE RDB$USER = 'PUBLIC' AND RDB$OBJECT_TYPE = 0
 GROUP BY RDB$PRIVILEGE
 ORDER BY RDB$PRIVILEGE;
SELECT RDB$USER_TYPE AS UTYPE, COUNT(DISTINCT RDB$USER) AS CNT_GRANTEES
  FROM RDB$USER_PRIVILEGES
 WHERE RDB$OBJECT_TYPE = 0
 GROUP BY RDB$USER_TYPE
 ORDER BY RDB$USER_TYPE;
'@
[System.IO.File]::WriteAllText($q, $sql, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "первые байты файла запроса:" (([System.IO.File]::ReadAllBytes($q))[0..7] -join ' ')

$ro = Read-Host 'Пароль учётной записи LOMBARD_RO'
& $isql -user LOMBARD_RO -pas $ro -e -m -i $q -o $out "localhost/3057:D:\PawnShop_DOL\DB\DOL.FDB"
Write-Host "код возврата isql: $LASTEXITCODE"
Get-Content -Path $out -Encoding UTF8
```

**Команда, как была запущена фактически (до правки брифа, строка подключения добавлена на месте):**

```powershell
$ro = Read-Host 'Пароль учётной записи LOMBARD_RO'
& $isql -user LOMBARD_RO -pas $ro -e -m -i $q -o $out "localhost/3057:D:\PawnShop_DOL\DB\DOL.FDB"
Write-Host "код возврата isql: $LASTEXITCODE"
Get-Content -Path $out -Encoding UTF8
```

**Что изменилось между брифовой формой шага и фактическим запуском.** В брифе (до правки
`ADR-036`) вызов `isql` для этого шага вовсе не нёс строки подключения к базе — падал бы
`Unable to open database`. Фактически запущенная команда несёт строку подключения
`"localhost/3057:D:\PawnShop_DOL\DB\DOL.FDB"` последним позиционным аргументом. SQL, учётная
запись и предикаты не менялись.

**Лог (код возврата isql: 0):**

```
SET LIST ON;
SELECT RDB$PRIVILEGE AS PRIV, COUNT(*) AS CNT_OBJECTS
  FROM RDB$USER_PRIVILEGES
 WHERE RDB$USER = 'PUBLIC' AND RDB$OBJECT_TYPE = 0
 GROUP BY RDB$PRIVILEGE
 ORDER BY RDB$PRIVILEGE;

PRIV D   CNT_OBJECTS 104
PRIV I   CNT_OBJECTS 104
PRIV R   CNT_OBJECTS 104
PRIV S   CNT_OBJECTS 107
PRIV U   CNT_OBJECTS 104

SELECT RDB$USER_TYPE AS UTYPE, COUNT(DISTINCT RDB$USER) AS CNT_GRANTEES
  FROM RDB$USER_PRIVILEGES
 WHERE RDB$OBJECT_TYPE = 0
 GROUP BY RDB$USER_TYPE
 ORDER BY RDB$USER_TYPE;

UTYPE 5   CNT_GRANTEES 1
UTYPE 8   CNT_GRANTEES 3
UTYPE 13  CNT_GRANTEES 2
```

**Встроенная проверка исправности.** Строка `S` дала `107` — ровно то число, что уже измерено
замером 2026-08-11 (`reference/T-0-5_readonly_measurement_2026-08-11.md`). Инструмент и предикат
подтверждены как исправные.

**Числа шага 6-ж — искомый факт.** `PUBLIC` несёт право `D` (delete) на `104` объектах, `I`
(insert) на `104`, `R` (references) на `104`, `S` (select) на `107`, `U` (update) на `104`.
Разных получателей собственных прав в базе — три типа: `5` (одна учётная запись), `8` (три
учётные записи), `13` (две учётные записи). **Расшифровка кодов типа получателя (`RDB$USER_TYPE`)
в этот артефакт не вносится** — она не измерена в этой задаче, любая расшифровка была бы
вымыслом (прямое указание архитектора).

**Исход (по критерию брифа).** Первый запрос — контрольная буква `S` = `107` совпала с прошлым
замером, буквы `I`, `U`, `D` впервые называют, на скольких объектах `PUBLIC` несёт права записи:
`104` на каждую из трёх. Второй запрос вернул строку на тип получателя без ошибки `Column unknown`
— колонка `RDB$USER_TYPE` в этой версии Firebird существует под тем же именем. Шаг пройден.

---

## Ссылка на решение

Оба лога разобраны и засчитаны решением `ADR-036` (`06_DECISIONS_LOG.md`): ремонт вызова
(добавление файла запроса и/или строки подключения к `isql`) не менял проверяемое утверждение,
поэтому логи действительны несмотря на то, что команды брифа на момент запуска были дефектны.

## Итог

Оба шага 6-е-БИС и 6-ж пройдены и закрывают доисполнение `T-0-5` по ПОПРАВКЕ 2. Факт, снятый
6-е-БИС: `SET TRANSACTION READ ONLY` на базе клиента режим переключает — третье объяснение тишины
старого (снятого) шага 6-е закрыто. Остаются два объяснения (отказ на уровне оператора против
отказа на уровне записи), различает их только замер `T-0-17` на собственном экземпляре Firebird —
в эту задачу он не входит. Факт, снятый 6-ж: `PUBLIC` несёт права записи (`D`/`I`/`U`) на `104`
объектах каждое при `SELECT` на `107`. **Переезд обращений к БД в класс A по факту закрытия
`T-0-5` не наступает** — условие переезда (`ADR-033`) требует трёх фактов разом: замера
`T-0-17`, `MON$`-строки о режиме транзакции (эта строка предъявлена этим артефактом) и обращения
через единственную точку доступа с белым списком операторов, которой ещё нет.
