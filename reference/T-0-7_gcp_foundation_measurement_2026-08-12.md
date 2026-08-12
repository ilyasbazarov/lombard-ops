# T-0-7 · Замер: GCP-фундамент в europe-west3

**Дата:** 2026-08-12 · **Бриф:** `briefs/T-0-7.md` · **Класс:** B (каждый ресурсный шаг — с отдельным
подтверждением владельца) · **Коммит на входе:** `e0f7e56`

## Расхождение брифа и контракта данных, закрытое архитектором

Бриф (на входе сессии) требовал **семь** таблиц и добавлял седьмым пунктом «справочник ликвидности».
`02_DATA_CONTRACTS.md §2` определяет **шесть** таблиц: `loans_raw`, `events`, `offers`,
`pricing_snapshots`, `vehicle_catalog`, `assessments`. Причина расхождения: «справочник ликвидности»
не отдельная таблица, а `vehicle_catalog` — `02 §2` называет справочником ликвидности именно её,
`03_BUSINESS_SPEC.md §3` озаглавлен «Справочник ликвидности (`vehicle_catalog`)». Двойной счёт одной
таблицы.

Закрыто вердиктом архитектора 2026-08-12, коммит `2c32c3b` (`briefs: T-0-7 — счёт таблиц приведён к
02 §2 (шесть, не семь)`) — проверено на диске (`git show --stat 2c32c3b`, текст брифа перечитан после
правки). `02_DATA_CONTRACTS.md` не правился — он источник истины и остаётся верным. Решение в журнал
не заводилось: дефект брифа, не правило.

## Шаг 1 — сверка входов и прав (класс A, только чтение)

Найдены и закрыты подтверждением владельца два расхождения с зафиксированными фактами:

1. Активный `gcloud config` проект на старте сессии — `msklad-bi-prod`, не
   `project-c451b48a-07ae-4de4-961`. Владелец подтвердил переключение:
   `gcloud config set project project-c451b48a-07ae-4de4-961`.
2. Роль текущего аккаунта — `roles/owner` (+ `roles/resourcemanager.projectMover`), не `editor`, как
   записано в `11_INFRA_FACTS.md` и `00_CHARTER.md §4`. Владелец подтвердил: это актуальный факт.
   `11_INFRA_FACTS` поправлен этим же session-блоком (`INFRA_PATCH`). `00_CHARTER.md` — STABLE
   документ, правка требует ADR архитектора; исполнитель её не вносит — открытый пункт, см.
   session-блок.

```
$ gcloud config list
[core]
account = ilyasbazarov4@gmail.com
project = project-c451b48a-07ae-4de4-961   (после переключения; было msklad-bi-prod)

$ gcloud auth list
ACTIVE  ACCOUNT
*       ilyasbazarov4@gmail.com

$ gcloud projects describe project-c451b48a-07ae-4de4-961
projectId: project-c451b48a-07ae-4de4-961
projectNumber: '450925595005'
lifecycleState: ACTIVE

$ gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 \
    --flatten="bindings[].members" --filter="bindings.members:ilyasbazarov4@gmail.com" \
    --format="table(bindings.role)"
ROLE
roles/owner
roles/resourcemanager.projectMover
```

## Шаг 2 — включение API (класс B, подтверждено владельцем)

Карточка подтверждения: включение BigQuery/Storage/Run/Functions/Scheduler/Secret Manager/Artifact
Registry/Cloud Build/IAM API в проекте `project-c451b48a-07ae-4de4-961`; откат — `gcloud services
disable <api>`.

```
$ gcloud services enable bigquery.googleapis.com storage.googleapis.com run.googleapis.com \
    cloudfunctions.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com \
    artifactregistry.googleapis.com cloudbuild.googleapis.com iam.googleapis.com \
    --project=project-c451b48a-07ae-4de4-961
Operation "operations/acf.p2-450925595005-fab05dca-ba7e-4497-9be4-9047ffa951a7" finished successfully.
exit: 0

$ gcloud services list --enabled --project=project-c451b48a-07ae-4de4-961
```
Все девять целевых API — в списке `--enabled` (плюс зависимости `containerregistry`,
`iamcredentials`, `pubsub`, `source`, подтянутые автоматически). Полный вывод см. в истории сессии.

## Шаг 3 — датасет и таблицы (класс B, подтверждено владельцем)

Карточка подтверждения: создание датасета `lombard_ops` и шести таблиц по `sql/ddl/lombard_ops.sql`
в `europe-west3`; откат — `bq rm -r -f lombard_ops`, данных нет.

DDL напечатан целиком в лог до применения (см. историю сессии и `sql/ddl/lombard_ops.sql`).

**Открытый гэп в DDL (не снят):** `02 §2` задаёт поле `*_discount` таблицы `assessments` как
wildcard — несколько колонок по факторам дисконта (`03_BUSINESS_SPEC.md §5`: кузов, толщиномер,
пробег, владельцы по ПТС), но не называет их английские имена для BigQuery. Владелец подтвердил:
не выдумывать, вопрос архитектору/владельцу отдельно. В DDL включена только явно названная
`total_discount`; колонки по факторам не добавлены. Снимается до `T-2-5` (форма осмотра).

```
$ bq mk --location=europe-west3 project-c451b48a-07ae-4de4-961:lombard_ops
Dataset 'project-c451b48a-07ae-4de4-961:lombard_ops' successfully created.

$ bq query --use_legacy_sql=false --project_id=project-c451b48a-07ae-4de4-961 < sql/ddl/lombard_ops.sql
Created project-c451b48a-07ae-4de4-961.lombard_ops.loans_raw
Created project-c451b48a-07ae-4de4-961.lombard_ops.events
Created project-c451b48a-07ae-4de4-961.lombard_ops.offers
Created project-c451b48a-07ae-4de4-961.lombard_ops.pricing_snapshots
Created project-c451b48a-07ae-4de4-961.lombard_ops.vehicle_catalog
Created project-c451b48a-07ae-4de4-961.lombard_ops.assessments
exit: 0

$ bq show --format=prettyjson project-c451b48a-07ae-4de4-961:lombard_ops | grep location
  "location": "europe-west3",

$ bq ls project-c451b48a-07ae-4de4-961:lombard_ops
       tableId        Type    Time Partitioning      Clustered Fields
 ------------------- ------- ------------------------ ------------------
  assessments         TABLE
  events              TABLE   DAY (field: timestamp)   contract_id
  loans_raw           TABLE
  offers               TABLE
  pricing_snapshots   TABLE
  vehicle_catalog     TABLE
```
Шесть строк — ровно те, что в `02 §2`. `events`: `PARTITION BY DATE(timestamp)`, `CLUSTER BY
contract_id` — дословно.

## Шаг 4 — бакеты (класс B, подтверждено владельцем)

Карточка подтверждения: создание трёх бакетов в `europe-west3`; откат —
`gcloud storage rm --recursive`, бакеты пусты.

```
$ gcloud storage buckets create gs://project-c451b48a-07ae-4de4-961-{photos,config,cfsource} \
    --project=project-c451b48a-07ae-4de4-961 --location=europe-west3 \
    --uniform-bucket-level-access --public-access-prevention

$ gcloud storage buckets describe gs://<bucket> \
    --format="value(name,location,public_access_prevention,uniform_bucket_level_access)"
project-c451b48a-07ae-4de4-961-photos     EUROPE-WEST3  enforced  True
project-c451b48a-07ae-4de4-961-config     EUROPE-WEST3  enforced  True
project-c451b48a-07ae-4de4-961-cfsource   EUROPE-WEST3  enforced  True
```

## Шаг 5 — сервисный аккаунт и роли (класс B, подтверждено владельцем)

Карточка подтверждения: создание `lombard-pipeline@` и привязка ролей; откат — удаление аккаунта и
снятие привязок.

**Отклонение от плана:** `bq add-iam-policy-binding` на датасете вернул `BigQuery error in
add-iam-policy-binding operation: This feature requires allowlisting` (fine-grained BQ IAM не
разрешён в проекте). Использован классический dataset ACL (`bq show` → добавление записи `{"role":
"WRITER", "userByEmail": <SA>}` → `bq update --source=...`) — тот же практический эффект (запись в
датасет), без project-level роли. Метод зафиксирован в `scripts/gcp_foundation.sh`.

```
$ gcloud iam service-accounts create lombard-pipeline --project=project-c451b48a-07ae-4de4-961 \
    --display-name=lombard-pipeline
Created service account [lombard-pipeline].

$ bq show --format=prettyjson project-c451b48a-07ae-4de4-961:lombard_ops → access[] содержит:
  {'role': 'WRITER', 'userByEmail': 'lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com'}

$ gcloud storage buckets get-iam-policy gs://<каждый из трёх бакетов>
  роль roles/storage.objectAdmin у serviceAccount:lombard-pipeline@... — во всех трёх

$ gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 \
    --flatten="bindings[].members" \
    --filter="bindings.members:lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com" \
    --format="table(bindings.role)"
ROLE
roles/secretmanager.secretAccessor
```
Привязки SA на уровне проекта — ровно одна роль, `secretAccessor`. Никакой `editor`/`owner`.

## Шаг 6 — секреты-заглушки (класс B, подтверждено владельцем)

Карточка подтверждения: создание трёх секретов с заглушками; откат — `gcloud secrets delete`.
Значения не печатались нигде — ни в терминале, ни в этом артефакте.

```
$ gcloud secrets create <name> --project=project-c451b48a-07ae-4de4-961 \
    --replication-policy=user-managed --locations=europe-west3 --data-file=-
Created version [1] of the secret [telegram-bot-token].
Created version [1] of the secret [firebird-readonly-creds].
Created version [1] of the secret [chat_id].

$ gcloud secrets list --project=project-c451b48a-07ae-4de4-961 \
    --format="table(name,replication.userManaged.replicas[0].location)"
NAME                     LOCATION
chat_id                  europe-west3
firebird-readonly-creds  europe-west3
telegram-bot-token       europe-west3

$ gcloud secrets versions list <name> --format="table(name,state)"
NAME  STATE
1     enabled
```
Три секрета, по одной версии каждый.

## Шаг 7 — сплошная проверка региона (класс A, только чтение)

Отрицательное утверждение «ресурсов вне `europe-west3` нет» — доказано сплошным списком плюс
положительный контроль.

```
$ bq ls -d project-c451b48a-07ae-4de4-961   (все датасеты проекта)
lombard_ops -> europe-west3

$ bq show project-c451b48a-07ae-4de4-961:lombard_ops   (положительный контроль)
lombard_ops location: europe-west3

$ gcloud storage buckets list --project=project-c451b48a-07ae-4de4-961 --format="table(name,location)"
NAME                                      LOCATION
project-c451b48a-07ae-4de4-961-cfsource   EUROPE-WEST3
project-c451b48a-07ae-4de4-961-config     EUROPE-WEST3
project-c451b48a-07ae-4de4-961-photos     EUROPE-WEST3

$ gcloud storage buckets describe gs://<каждый бакет>   (положительный контроль)
project-c451b48a-07ae-4de4-961-photos     EUROPE-WEST3
project-c451b48a-07ae-4de4-961-config     EUROPE-WEST3
project-c451b48a-07ae-4de4-961-cfsource   EUROPE-WEST3
```
Сплошной список датасетов проекта содержит ровно один датасет (`lombard_ops`), сплошной список
бакетов — ровно три (все три созданных). Оба совпадают с положительным контролем по конкретному
ресурсу. Ресурсов вне `europe-west3` нет.

## Приёмка — сводка

| Критерий | Статус |
|---|---|
| Каждый ресурс предъявлен командой чтения с именем и регионом | да, см. шаги 2–7 |
| `bq ls lombard_ops` печатает шесть таблиц (`02 §2`); `bq show` — `europe-west3` | да |
| Три бакета предъявлены с локацией и без публичного доступа | да |
| SA предъявлен списком ролей; `editor`/`owner` в списке нет | да |
| Три секрета предъявлены именами и числом версий; значения не напечатаны | да |
| Шаг 7 — сплошной список с положительным контролем | да |
| `11_INFRA_FACTS` заполнен через INFRA_PATCH фактами с датами | да, см. session-блок |
| Ни один критерий не закрыт кодом возврата | да — везде печать содержимого, не только `exit: 0` |

## Открытые пункты, не закрытые этой сессией

1. **`00_CHARTER.md §4`** утверждает «Ilyas — editor, не owner» — фактически owner. STABLE документ,
   правка требует ADR архитектора, не входит в мандат исполнителя.
2. **DDL `assessments`** не содержит колонок по факторам дисконта (`*_discount` из `02 §2`) — имена
   не названы ни в `02`, ни в `03`. Снимается вопросом архитектору/владельцу до `T-2-5`.
