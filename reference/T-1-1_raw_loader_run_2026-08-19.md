# T-1-1 · Приземление выгрузок в слой сырья BigQuery + guard при загрузке — прогон 2026-08-19

**Статус сессии: класс A ИСПОЛНЕН (шаги 1-6, 11), класс B НЕ ИСПОЛНЕН (шаги 7-10, ждут карточек
подтверждения владельца), шаг 12 — CONTEXT GAP, названо явно, не обойдено.**

## Шаг 1 — генератор DDL (`connector/generate_raw_ddl.py`)

Чистая функция, без сети. Правило типов — закрытый список семи кодов Firebird (`ADR-083` п.4).
Реальный `connector/mapping.json`: 9 таблиц, 124 колонки, все коды входят в закрытый список
(`7, 8, 12, 16, 27, 35, 37`) — проверено сплошным перебором (`test_generate_raw_ddl.py`, проверка 8).

Сгенерированный артефакт: `sql/ddl/lombard_ops_raw.sql`, 9 `CREATE TABLE IF NOT EXISTS`, имена
`raw_contracts`, `raw_contracts_terms`, `raw_subjects`, `raw_custom_fields_values`,
`raw_dir_custom_fields`, `raw_tables_table`, `raw_contract_states`, `raw_deposit_types`,
`raw_operations` — совпадают с `ADR-083` п.3 дословно. Каждая таблица несёт `loaded_at TIMESTAMP
NOT NULL` и `source_blob STRING NOT NULL`.

## Шаг 2 — guard на загрузке (`connector/raw_loader/guard.py`)

Сверка множества пар `(имя, тип)` эталон/живая схема BigQuery, через подменяемую фабрику клиента.
Расхождение → `SchemaLoadGuardMismatch` с именем таблицы и обеими сторонами.

## Шаг 3 — загрузчик (`connector/raw_loader/loader.py`)

Обобщение `functions/cf_daily/bq_loader` на произвольную таблицу: чтение NDJSON из GCS, добавление
`loaded_at`/`source_blob` каждой строке, загрузка явным списком колонок (`WriteDisposition.WRITE_APPEND`,
`SourceFormat.NEWLINE_DELIMITED_JSON`), без autodetect.

## Шаг 4 — копия Telegram (`connector/raw_loader/telegram_send.py`)

Байт-в-байт копия `functions/cf_daily/telegram_send.py` (`diff` — 0 расхождений, проверено перед
коммитом). Причина копирования, а не импорта — `ADR-078` пп.4-5.

## Шаг 5 — точка входа (`connector/raw_loader/main.py`)

**Инженерное решение, не названное брифом дословно и зафиксированное здесь явно:** деплой идёт
`--source=connector/raw_loader` (шаг 8), поэтому импорт `connector/generate_raw_ddl.py` и чтение
`connector/mapping.json` из точки входа НЕВОЗМОЖНЫ внутри контейнера — тот же класс дефекта, что
стоил раунда деплоя `cf-daily` (`ADR-078`). Решение — та же копия, что и `telegram_send.py`:
`connector/raw_loader/generate_raw_ddl.py` и `connector/raw_loader/mapping.json` — byte-копии
источников истины `connector/generate_raw_ddl.py`/`connector/mapping.json` (сверено `diff`, 0
расхождений на момент коммита). Синхронизация копий — явный шаг `part2` в
`scripts/T-1-1_deploy.sh`, непосредственно перед `gcloud run jobs deploy`, так что деплою всегда
достаётся свежая копия.

**Решение исполнителя по стопу прогона (шаг 5 брифа, п. «любой упавший шаг для отдельной таблицы»):
любой отказ (guard-расхождение ИЛИ транспортный — GCS/BQ/сеть) останавливает ВЕСЬ прогон, не только
упавшую таблицу.** Обоснование — докстринг `connector/raw_loader/main.py`: частичная загрузка (часть
таблиц свежая, часть — вчерашняя) создаёт скрытую рассинхронизацию `loaded_at` между таблицами слоя
сырья, которую слой канонизации (`T-1-2`) не видит и не может обнаружить сам; дешевле подождать
следующие сутки целиком, чем распутывать разъехавшиеся даты позже.

## Шаг 6 — `requirements.txt`

`connector/raw_loader/requirements.txt`: `google-cloud-storage`, `google-cloud-bigquery`,
`google-cloud-secret-manager`. Без `functions-framework` (не Cloud Function).

## Локальные тесты — все зелёные (вывод команд, не пересказ)

```
$ cd connector && python3 test_generate_raw_ddl.py
[пройдено]  1: raw_table_name — нижний регистр, префикс raw_
[пройдено]  2: bq_type_for_column — все семь закрытых кодов дают верный тип
[пройдено]  3: код типа вне закрытого списка (999) даёт UnknownTypeCode с именем таблицы/колонки/кода
[пройдено]  3-БИС: обратный замер — нетронутая фикстура генератор проходит без исключения (контраст к 3)
[пройдено]  4: generate_table_ddl — служебные колонки loaded_at/source_blob присутствуют
[пройдено]  5: generate_raw_ddl на фикстуре — одна CREATE TABLE на таблицу отпечатка
[пройдено]  6: подмена одного кода фикстуры (8 -> 999) стопит генератор целиком — отказ лога
[пройдено]  7: load_schema_fingerprint — путь к отсутствующему разделу даёт ValueError (CONTEXT GAP)
[пройдено]  8: реальный connector/mapping.json — 9 таблиц, 124 колонки, все коды из закрытого списка
всего проверок: 9; провалено 0

$ cd connector/raw_loader && python3 test_guard.py
[пройдено]  1: expected_schema_pairs/live_schema_pairs — mode игнорируется, регистр нормализован
[пройдено]  2: подмена одного типа в живой схеме -> SchemaLoadGuardMismatch, лог отказа с обеими сторонами
[пройдено]  3 (обратный замер, контраст к 2): нетронутая живая схема — guard проходит без исключения
всего проверок: 3; провалено 0

$ cd connector/raw_loader && python3 test_loader.py
[пройдено]  1: parse_gs_path разбирает gs://bucket/blob корректно
[пройдено]  1-БИС: parse_gs_path отбивает не-gs:// путь (контраст с 1)
[пройдено]  2: add_loader_columns — loaded_at и source_blob добавлены каждой строке
[пройдено]  3: load_table_blob — фикстура из 3 строк, счёт совпадает, схема БЕЗ autodetect
всего проверок: 4; провалено 0

$ cd connector/raw_loader && python3 test_telegram_send.py
[пройдено]  1: send_message — успешный ответ Bot API возвращает message_id строкой
[пройдено]  2: send_message — Bot API отвечает ok:false -> TelegramSendError, не тихий проход
[пройдено]  3: модуль telegram_send.py не читает секреты сам — 0 совпадений 'secretmanager'
всего проверок: 3; провалено 0

$ cd connector/raw_loader && python3 test_main.py
GUARD ОСТАНОВИЛ ПРОГОН на таблице CONTRACTS: SchemaLoadGuardMismatch: таблица raw_contracts — ...
[пройдено]  1: все девять таблиц совпадают со схемой — прогон завершается без исключения, 9 загрузок
[пройдено]  2: расхождение на ПЕРВОЙ таблице (CONTRACTS) — прогон останавливается ЦЕЛИКОМ, алерт отправлен, остальные восемь НЕ тронуты (0 загрузок)
всего проверок: 2; провалено 0
```

Все 5 файлов тестов — 21 проверка, 0 провалено, коды возврата всех прогонов — 0.

## Шаг 11 — отрицательная проба guard'а (класс A, локально, без деплоя)

### Генератор (шаг 1): мутация `CONTRACTS.DEPOSIT_TYPE` 8 → 999

```
до мутации: ['DEPOSIT_TYPE', 8, 4, 0]
после мутации: ['DEPOSIT_TYPE', 999, 4, 0]

--- Прогон генератора на МУТИРОВАННОМ mapping.json (ожидается отказ) ---
[ОТКАЗ, как и ожидалось] UnknownTypeCode: таблица CONTRACTS, колонка DEPOSIT_TYPE, код типа 999
вне закрытого списка ADR-083 п.4 (7, 8, 12, 16, 27, 35, 37) — изменение схемы вендора, стоп,
не подстановка похожего типа

--- Обратный замер: прогон генератора на НЕТРОНУТОМ mapping.json (ожидается проход) ---
[ПРОШЛО, как и ожидалось] DDL сгенерирован, 9 таблиц, UnknownTypeCode не поднят
```

### Guard (шаг 2): моковая живая схема `raw_contract_states.state_id` INT64 → STRING

```
--- Прогон guard'а на МОКОВОЙ живой схеме, отличной от построенной (ожидается отказ) ---
[ОТКАЗ, как и ожидалось] SchemaLoadGuardMismatch: таблица raw_contract_states —
эталон=[('code','STRING'),('loaded_at','TIMESTAMP'),('sort_order','INT64'),('source_blob','STRING'),
('state_id','INT64')]
ИЗМЕРЕНО=[('code','STRING'),('loaded_at','TIMESTAMP'),('source_blob','STRING'),('state_id','STRING')]
— загрузка ОСТАНОВЛЕНА
[ДОСТАВЛЕНО, тестовый мок] message_id=4242, url содержит токен=True
текст сообщения: raw-loader: guard схемы остановил прогон на таблице raw_contract_states:
SchemaLoadGuardMismatch: ... — загрузка ОСТАНОВЛЕНА

--- Обратный замер: guard на НЕТРОНУТОЙ живой схеме, равной построенной (ожидается проход) ---
[ПРОШЛО, как и ожидалось] guard не поднял исключения на нетронутом эталоне
```

Оба отказа (генератор — код типа вне списка; guard — расхождение живой схемы с доставленным
тестовым алертом) и оба обратных замера предъявлены логом — критерии приёмки по шагу 11 закрыты.

## Шаг 12 — прицеп `ADR-063` R3 — `CONTEXT GAP`

```
$ ls tools/hooks/
answer_check.sh  answer_extract.py  answer_form_reminder.sh  answer_judge.sh  pre-commit  selftest.sh
$ grep -n "R3\|внешн.*источник\|external.*source" tools/hooks/pre-commit
(0 совпадений строкой "R3"/проверки внешних источников)
```

**`CONTEXT GAP: хук ADR-063 R3 не найден в tools/hooks/`.** На момент этой сессии в каталоге хуков
нет проверки «код с литеральным путём во внешний каталог данных требует строки в реестре внешних
источников». Путь `gs://${PROJECT_ID}-cfsource/agent/...`, употреблённый в этом коммите
(`connector/raw_loader/main.py`, `find_latest_table_blob`), строкой в `11_INFRA_FACTS.md` заведён
задачей `T-0-8` (бакет `${PROJECT_ID}-cfsource`, раздел «GCP», строка «Бакеты»; способ и формат
блоба — раздел «Способ запуска агента») — не новый объект. Хук не написан этой сессией (брифом
запрещено писать хук в обход отдельной задачи на него) — гэп называется архитектору отдельной
строкой в session-блоке, не обходится молчаливым пропуском критерия приёмки.

## Класс B, карточка 1 — DDL слоя сырья ИСПОЛНЕНО 2026-08-19, подтверждено владельцем

`bq query --use_legacy_sql=false --project_id=project-c451b48a-07ae-4de4-961 < sql/ddl/lombard_ops_raw.sql`.
Вывод — девять `Created project-c451b48a-07ae-4de4-961.lombard_ops.raw_<table>`, ни одной ошибки.
Обратная проверка `bq ls --project_id=project-c451b48a-07ae-4de4-961 lombard_ops | grep raw_` печатает
все девять имён (`raw_contracts`, `raw_contracts_terms`, `raw_subjects`, `raw_custom_fields_values`,
`raw_dir_custom_fields`, `raw_tables_table`, `raw_contract_states`, `raw_deposit_types`,
`raw_operations`) типом `TABLE`. Откат — `bq rm -t lombard_ops.raw_<table>` по каждой из девяти;
остальные шесть таблиц датасета не затронуты.

## Класс B, карточка 2 — деплой Cloud Run Job ИСПОЛНЕНО 2026-08-19, подтверждено владельцем

Первый прогон `gcloud run jobs deploy --source=connector/raw_loader --build-service-account=...`
отбит `unrecognized arguments` — флаг существует у `gcloud functions deploy`, не у `gcloud run jobs
deploy` (SDK 577.0.0, проверено `--help` во всех каналах, включая beta). Скрипт переписан на
двухшаговый билд+деплой: `gcloud builds submit connector/raw_loader --pack=image=<IMAGE>
--service-account=projects/.../serviceAccounts/lombard-build@…` (репозиторий образа —
`cloud-run-source-deploy`, тот же, что использует `--source`-деплой неявно), затем `gcloud run jobs
deploy raw-loader --image=<IMAGE> --service-account=lombard-pipeline@…`. Второй прогон (`--tag` без
Dockerfile) тоже отбит `Invalid value for [source]: Dockerfile required` — в `connector/raw_loader/`
Dockerfile'а нет по замыслу (buildpacks), исправлено на `--pack=image=...`.

Третий прогон — SUCCESS: билд `58da7637-…` под `lombard-build`, образ
`europe-west3-docker.pkg.dev/project-c451b48a-07ae-4de4-961/cloud-run-source-deploy/raw-loader`.
`gcloud run jobs describe raw-loader` подтверждает: `Service account:
lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com`, `Image:` тот же адрес,
`Env vars: PROJECT_ID`, `Executed 0 times`. Откат — `gcloud run jobs delete raw-loader
--region=europe-west3`.

## Класс B, карточка 3 — invoker + Cloud Scheduler ИСПОЛНЕНО 2026-08-19, подтверждено владельцем

`gcloud run jobs add-iam-policy-binding raw-loader --member=serviceAccount:lombard-pipeline@…
--role=roles/run.invoker` прошло без исправлений (команда — как в скрипте). `gcloud scheduler jobs
create http raw-loader-trigger` — тоже без исправлений. `describe` подтверждает: `schedule: 0 4 * *
*`, `timeZone: Asia/Bishkek`, `state: ENABLED`, `uri: .../jobs/raw-loader:run`, `oidcToken.
serviceAccountEmail: lombard-pipeline@…`. `scheduleTime: 2026-08-19T22:00:00Z` = 04:00 Бишкек
2026-08-20, совпадает с расписанием побуквенно. Первый автоматический прогон — не раньше этого
момента; шаг 10 (работоспособность нитки на живых данных) не проверен. Откат — `gcloud scheduler
jobs delete raw-loader-trigger --location=europe-west3` и снятие invoker-биндинга.

## Класс B — все три карточки `T-1-1` исполнены. Строка задачи остаётся `todo` до шага 10

## Проверка на секреты перед коммитом

```
$ grep -n "BEGIN\|PRIVATE KEY\|LOMBARD_RO" connector/raw_loader/*.py connector/*.py scripts/T-1-1_deploy.sh
(0 совпадений)
```

Ни одного секретного значения (токен, боевой `chat_id`) в коммитируемых файлах нет.
