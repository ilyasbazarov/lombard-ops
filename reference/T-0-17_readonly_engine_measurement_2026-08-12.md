# T-0-17 — замер семантики `SET TRANSACTION READ ONLY` на собственном Firebird 2.5.9

**Дата:** 2026-08-12 · **Задача:** T-0-17 · **Коммит на входе:** a0a3b0d064d3761f7e89e227038699cb730826e9
(`git rev-parse HEAD`)

Площадка — контейнер `jacobalberty/firebird:2.5.9-sc` под `colima` (`--arch x86_64 --cpu 2 --memory 4
--disk 20`) на машине Ilyas. Никакой команды к контуру клиента не выполнялось: ни сервер ERP, ни база
PawnShop, ни RDP этой сессией не затрагивались. Площадка снесена по завершении (шаг 9).

---

## Шаг 1 — сверка площадки

```
uname -m            → arm64
sw_vers -productVersion → 15.3.1
brew --version       → Homebrew 6.0.17
which colima docker  → /opt/homebrew/bin/colima, /opt/homebrew/bin/docker
```

**Расхождение со входами брифа, зафиксировано как факт (не стоп):**
- Homebrew версия `6.0.17`, во входах брифа названа `6.0.14` — минорное обновление между 2026-08-11 и
  2026-08-12, не относится к предмету замера.
- `colima` и `docker` УЖЕ установлены и уже существовал остановленный профиль `colima` с параметрами
  `x86_64 / 2 CPU / 4GiB / 20GiB` — теми же, что предписывает шаг 2 брифа. Судя по совпадению
  параметров, оснастка была подготовлена ранее (предыдущей прерванной попыткой той же задачи), но не
  запущена. Установка `brew install colima docker` этой сессией не выполнялась — не требовалась.
- Firebird на хосте по-прежнему отсутствует (`isql`, `fbsvcmgr`, `gfix` не найдены,
  `/Library/Frameworks/Firebird.framework` нет) — совпадает со входами.

## Шаг 2 — запуск контейнерного движка

Первый `colima start --arch x86_64 --cpu 2 --memory 4 --disk 20` завершился ошибкой на стадии
провижининга докера:
```
time="2026-08-12T03:06:54+06:00" level=fatal msg="error starting docker: cannot restart, VM not previously started"
```
После `colima stop` (чистое завершение, `The instance colima has shut down`) повторный
`colima start` с теми же параметрами прошёл штатно, `docker info` отдал сведения о демоне:
```
Server Version: 29.5.2
Architecture: x86_64
Operating System: Ubuntu 24.04.4 LTS
CPUs: 2
Total Memory: 3.819GiB
```

## Шаг 3 — образ ровно версии 2.5.9

```
docker pull jacobalberty/firebird:2.5.9-sc
```
Тег найден и забран:
```
Status: Downloaded newer image for jacobalberty/firebird:2.5.9-sc
docker.io/jacobalberty/firebird:2.5.9-sc
```

## Шаг 4 — подъём контейнера и версия сервера

```
docker run -d --name fb259 jacobalberty/firebird:2.5.9-sc
```
Первый запуск контейнера завершился самопроизвольно (`docker ps -a` → `Exited (137)`, лог без строки
отказа — похоже на убийство процессом ядра гостевой VM, конкретная причина не установлена и не
относится к предмету замера). `docker start fb259` поднял его повторно и он оставался живым до конца
сессии (`Up`, `health: starting` → далее использовался без проблем).

Путь к `isql` измерен, а не угадан:
```
docker exec fb259 sh -c 'command -v isql || ls /usr/local/firebird/bin /opt/firebird/bin 2>/dev/null'
→ /usr/local/firebird/bin/isql среди прочих утилит (fbsvcmgr, gfix, gbak, ...)
```

Версия сервера предъявлена:
```
docker exec fb259 /usr/local/firebird/bin/isql -z -quiet -i /dev/null
→ ISQL Version: LI-V2.5.9.27139 Firebird 2.5
```
Содержит `2.5.9` — критерий приёмки выполнен, прогон засчитывается.

## Шаг 5 — выброшенная база и одна строка

Скрипт `scripts/readonly_probe_setup.sql`, прогон `isql -i` внутри контейнера:
```
Use CONNECT or CREATE DATABASE to specify a database

   CNT_SETUP 
============ 
           1
```
Строка `Use CONNECT or CREATE DATABASE to specify a database` — банер `isql` в не-`quiet`-режиме
(проверено отдельно: та же команда с флагом `-quiet` эту строку не печатает, при этом
`SELECT COUNT(*) FROM PROBE` после явного `CONNECT` в quiet-режиме отдаёт то же `1`). Не является
отказом: `CNT_SETUP = 1` подтверждён и повторной выборкой (`CNT_VERIFY = 1`). Дальше по сессии
используется `isql -quiet`, чтобы этот баннер не путался со строками отказа проб.

## Шаг 6 — положительный контроль в обычной транзакции (оба предиката)

Скрипт (одно подключение, оба `UPDATE` подряд, без `SET TRANSACTION READ ONLY`):
```sql
CONNECT '/tmp/probe.fdb' USER 'SYSDBA' PASSWORD '...';
UPDATE PROBE SET ID = ID WHERE 1 = 0;
UPDATE PROBE SET ID = ID WHERE ID = 1;
COMMIT;
SELECT COUNT(*) AS CNT_AFTER_RW FROM PROBE;
```
Результат (`isql -quiet`, код возврата `0`):
```
CNT_AFTER_RW 
============ 
           1
```
Тишина по обеим `UPDATE`, `CNT_AFTER_RW = 1` — число строк не изменилось. Положительный контроль
пройден: проба исправна, оба предиката реально исполнимы движком в обычной транзакции.

## Шаг 7 — измеряемое, проба с НУЛЕВЫМ предикатом (отдельный прогон, чистый файл результата)

Скрипт `scripts/readonly_probe_zero.sql` (плюс `CONNECT` в реальном прогоне):
```sql
CONNECT '/tmp/probe.fdb' USER 'SYSDBA' PASSWORD '...';
COMMIT;
SET TRANSACTION READ ONLY;
SELECT MON$READ_ONLY AS RO_FLAG FROM MON$TRANSACTIONS WHERE MON$TRANSACTION_ID = CURRENT_TRANSACTION;
UPDATE PROBE SET ID = ID WHERE 1 = 0;
COMMIT;
```
Файл результата очищен перед запуском (`rm -f /tmp/result_zero.log`). Код возврата `0`. Содержимое
файла результата дословно:
```
RO_FLAG 
======= 
      1
```
Колонка `RO_FLAG` напечаталась без ошибки `Column unknown` — подбор имени не понадобился.
`RO_FLAG = 1` — движок подтверждает: транзакция действительно в режиме `READ ONLY`.
После `UPDATE PROBE SET ID = ID WHERE 1 = 0;` — **тишина**: ни строки `Statement failed`, ни любого
другого текста отказа, ни до, ни после `COMMIT`.

## Шаг 8 — измеряемое, проба с предикатом НА ОДНУ СТРОКУ (отдельный прогон, чистый файл результата)

Скрипт `scripts/readonly_probe_row.sql` (плюс `CONNECT`):
```sql
CONNECT '/tmp/probe.fdb' USER 'SYSDBA' PASSWORD '...';
COMMIT;
SET TRANSACTION READ ONLY;
UPDATE PROBE SET ID = ID WHERE ID = 1;
COMMIT;
SELECT COUNT(*) AS CNT_AFTER_RO FROM PROBE;
```
Файл результата очищен перед запуском (`rm -f /tmp/result_row.log`). Код возврата `1`.

Строка отказа на стандартном выводе, дословно:
```
Statement failed, SQLSTATE = 42000
attempted update during read-only transaction
After line 3 in file /tmp/readonly_probe_row_run.sql
```
Файл результата (`/tmp/result_row.log`) дословно:
```
CNT_AFTER_RO 
============ 
           1
```
`CNT_AFTER_RO = 1` — строка не задета (отказ случился раньше записи).

## Шаг 9 — снос площадки

```
docker rm -f fb259   → fb259
colima stop          → "The instance colima has shut down"
colima status         → "colima is not running"
docker ps -a           → "no such file or directory" (демон недоступен, площадки нет)
```
Выброшенная база `/tmp/probe.fdb` уехала вместе с контейнером. В репозитории от неё остались только
три скрипта и этот лог.

---

## Вердикт по таблице исходов брифа

**Тишина в шаге 7, отказ в шаге 8→ отказ на уровне ЗАПИСИ (изменяемой записи), не на уровне
оператора.**

Прямой ответ: **второй рубеж защиты СУЩЕСТВУЕТ.** `SET TRANSACTION READ ONLY` в Firebird 2.5.9
действительно отбивает попытку изменения — но отбивает её на уровне записи, которую оператор
реально задевает, а не на уровне синтаксиса самого `UPDATE`. Отсюда прямо следует и то, что проба
шага 6-е задачи `T-0-5` (предикат `WHERE 1 = 0`, нулевые задетые строки) была структурно
неразличающей: она физически не могла дойти до записи и поймать отказ, независимо от того, действует
режим или нет. Тишина в том логе — не опровержение компенсирующего контроля, а следствие формы самой
пробы. Это ровно второе из трёх объяснений, названных `ADR-033`.

Это закрывает строку `Q-17`.
