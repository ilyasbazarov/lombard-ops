# ЗАМЕР · T-1-0 шаг 6 · билд-сервис-аккаунт деплоя `cf-daily` · 2026-08-18

**Объект замера определён:** проект GCP `project-c451b48a-07ae-4de4-961` (`11_INFRA_FACTS.md`,
раздел «GCP», строка `PROJECT_ID`) и упавшая сборка Cloud Build в нём — существовали до этой
сессии. Идентификатор сборки НЕ взят из текста запуска: он получен собственным листингом
(замер 5 ниже).

**Роль и мандат:** архитектор, класс A — только чтение облака (`describe`/`list`/`get-iam-policy`).
Ни одной операции записи в GCP этой сессией не исполнено.
**Коммит на входе:** `dc1d7c9d7bdf4c71834d381fa845c563ac6a6d5b`.

---

## 1. Что мерилось и зачем

Шаг 6 `briefs/T-1-0.md` (класс B, деплой Cloud Function `cf-daily`) упал на этапе Cloud Build:
`Could not build the function due to a missing permission on the build service account`.
Вопрос замера: какой именно сервисный аккаунт исполнял сборку и почему у него нет прав — это
недостающий факт (закрывается замером) или неопределённый объект (`ADR-061`, закрывается только
владельцем).

## 2. Замер 1 — сервисные аккаунты проекта

```
$ gcloud iam service-accounts list --project=project-c451b48a-07ae-4de4-961
DISPLAY NAME                        EMAIL                                                                    DISABLED
Default compute service account     450925595005-compute@developer.gserviceaccount.com                       False
App Engine default service account  project-c451b48a-07ae-4de4-961@appspot.gserviceaccount.com               False
lombard-pipeline                    lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com  False
```

**Дефолтный Compute Engine SA в проекте СУЩЕСТВУЕТ и не отключён.** Это опровергает утверждение,
пришедшее текстом запуска сессии («SA отсутствует вовсе, `gcloud iam service-accounts list` его не
показал») — расхождение названо здесь поимённо по `ADR-027`, вердикт строится на строке вывода
выше, а не на пересказе.

## 3. Замер 2 — политика организации о грантах дефолтным SA

```
$ gcloud resource-manager org-policies describe \
    constraints/iam.automaticIamGrantsForDefaultServiceAccounts \
    --project=project-c451b48a-07ae-4de4-961 --effective
booleanPolicy:
  enforced: true
constraint: constraints/iam.automaticIamGrantsForDefaultServiceAccounts
```

Ограничение ДЕЙСТВУЕТ. Смысл ограничения — дефолтные сервисные аккаунты (`*-compute@developer`,
`*@appspot`) НЕ получают автоматической роли уровня проекта при создании. Это третья измеренная
орг-политика клиента (после `iam.disableServiceAccountKeyCreation`, `ADR-049`, и
`iam.workloadIdentityPoolProviders`, `ADR-050`) и вторая ограничивающая.

Обратный контроль исправности инструмента — соседнее ограничение отдаётся тем же вызовом и
НЕ действует, то есть вывод «enforced: true» не является формой отказа команды:

```
$ gcloud resource-manager org-policies describe constraints/iam.disableServiceAccountCreation \
    --project=project-c451b48a-07ae-4de4-961 --effective
booleanPolicy: {}
constraint: constraints/iam.disableServiceAccountCreation
```

## 4. Замер 3 — политика проекта по каждому из трёх аккаунтов

```
$ gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 \
    --flatten="bindings[].members" --format="table(bindings.role)" \
    --filter="bindings.members:450925595005-compute@developer.gserviceaccount.com"
<пустой вывод — ни одной строки>

$ ... --filter="bindings.members:450925595005@cloudbuild.gserviceaccount.com"
ROLE
roles/cloudbuild.builds.builder

$ ... --filter="bindings.members:lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com"
ROLE
roles/secretmanager.secretAccessor
```

Пустой вывод по первому фильтру подтверждён обратным запросом — тот же вызов без фильтра печатает
11 разных членов политики, инструмент исправен:

```
$ gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 \
    --flatten="bindings[].members" --format="value(bindings.members)" | sort -u
serviceAccount:450925595005@cloudbuild.gserviceaccount.com
serviceAccount:lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
serviceAccount:service-450925595005@containerregistry.iam.gserviceaccount.com
serviceAccount:service-450925595005@gcf-admin-robot.iam.gserviceaccount.com
serviceAccount:service-450925595005@gcp-sa-artifactregistry.iam.gserviceaccount.com
serviceAccount:service-450925595005@gcp-sa-cloudbuild.iam.gserviceaccount.com
serviceAccount:service-450925595005@gcp-sa-cloudscheduler.iam.gserviceaccount.com
serviceAccount:service-450925595005@gcp-sa-pubsub.iam.gserviceaccount.com
serviceAccount:service-450925595005@serverless-robot-prod.iam.gserviceaccount.com
user:ilyasbazarov4@gmail.com
user:omegalombard2023@gmail.com
```

**Дефолтный compute SA существует и не несёт НИ ОДНОЙ роли уровня проекта** — ровно то, что
предписывает действующая политика замера 3.

## 5. Замер 4 — РЕШАЮЩИЙ: под каким аккаунтом шла упавшая сборка

```
$ gcloud builds list --region=europe-west3 --project=project-c451b48a-07ae-4de4-961 --limit=5
ID                                    CREATE_TIME                DURATION  SOURCE  IMAGES  STATUS
3b095e85-6052-4f39-afeb-829aa19a6e5c  2026-08-18T10:27:22+00:00  18S       -       -       FAILURE

$ gcloud builds describe 3b095e85-6052-4f39-afeb-829aa19a6e5c --region=europe-west3 \
    --project=project-c451b48a-07ae-4de4-961 \
    --format="yaml(serviceAccount,status,failureInfo)"
failureInfo:
  detail: 'Build step failure: build step 0 "europe-west3-docker.pkg.dev/serverless-runtimes/utilities/gcs-fetcher:base_20260522_18_04_RC00"
    failed: step exited with non-zero status: 3'
  type: USER_BUILD_STEP
serviceAccount: projects/project-c451b48a-07ae-4de4-961/serviceAccounts/450925595005-compute@developer.gserviceaccount.com
status: FAILURE
```

**Сборку исполнял дефолтный compute SA, у которого ноль ролей.** Упал нулевой шаг — `gcs-fetcher`,
то есть скачивание исходника функции из бакета; до кода функции сборка не дошла ни на шаг. Отказ
объяснён целиком и без остатка: политика организации не даёт дефолтному SA прав, платформа
назначает его билд-аккаунтом по умолчанию, у него нет `storage.objects.get` на бакете исходников.

## 6. Замер 5 — чем закрывается: роль, которая уже выдана легаси-аккаунту Cloud Build

`450925595005@cloudbuild.gserviceaccount.com` несёт `roles/cloudbuild.builds.builder` (замер 3).
Состав роли — 79 разрешений, среди них все четыре, которых не хватило сборке:

```
$ gcloud iam roles describe roles/cloudbuild.builds.builder --format="yaml(includedPermissions)" \
    | grep -nE "logging\.logEntries\.create|storage\.objects\.get$|storage\.objects\.create|artifactregistry\.repositories\.uploadArtifacts"
37:- artifactregistry.repositories.uploadArtifacts
62:- logging.logEntries.create
75:- storage.objects.create
77:- storage.objects.get
```

Обратный контроль: заведомо посторонняя строка в том же выводе не находится —
`grep -c "bigquery.datasets.delete"` даёт `0`, то есть совпадения выше не артефакт grep'а.

## 7. Замер 6 — флаг, которым билд-аккаунт называется явно, и права исполнителя деплоя

```
$ gcloud functions deploy --help | grep -n "build-service-account"
26:        [--build-service-account=BUILD_SERVICE_ACCOUNT
27:          | --clear-build-service-account]
359:       --build-service-account=BUILD_SERVICE_ACCOUNT
367:       --clear-build-service-account
```

Установленный `gcloud` флаг поддерживает. Учётная запись, которой исполняется деплой, несёт
`roles/owner` (замер той же политики, фильтр `user:ilyasbazarov4@gmail.com` →
`roles/owner`, `roles/resourcemanager.projectMover`) — права «действовать от имени» билд-аккаунта
у неё есть по построению роли.

## 8. Замер 7 — состояние ресурса после упавшего деплоя (не-идемпотентность, `05 §I`)

```
$ gcloud functions describe cf-daily --region=europe-west3 --gen2 \
    --project=project-c451b48a-07ae-4de4-961 --format="value(state,serviceConfig.serviceAccountEmail)"
CRITICAL: Function has the following conditions:
  [ERROR] Cloud Run service .../services/cf-daily for the function was not found.
          The function will not work correctly. Please redeploy.
FAILED
```

**Огрызок ресурса остался:** функция `cf-daily` числится в состоянии `FAILED`, сервиса Cloud Run за
ней нет. Слепого повтора это не запрещает (платформа сама просит redeploy), но откат карточки
подтверждения обязан называть удаление огрызка, а не только удаление успешного деплоя.

## 9. Что НЕ измерено и угадыванию не подлежит

Примет ли платформа явно названный легаси-аккаунт Cloud Build как билд-аккаунт функции второго
поколения и пройдёт ли сборка целиком — **этим замером не установлено**. Различающая проверка ровно
одна: фактический деплой с флагом (класс B). Отказ там → стоп и вопрос владельцу, а не подбор
второго аккаунта наугад.

## 10. Классификация (полный разбор — `ADR-076`)

Строкой в `07_GAPS.md` этот случай НЕ заводится, и это решение, а не умолчание: неопределённого
объекта (`ADR-061`) здесь нет — объект платформенный, определён и измерен семью замерами выше,
нашего кода, который его читает, не существует; недостающего у владельца знания не осталось.
Остаток — одно действие класса B, а его носитель карточка подтверждения, не реестр вопросов.
