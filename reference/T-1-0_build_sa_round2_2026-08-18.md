# ЗАМЕР · T-1-0 шаг 6 · раунд 2 · существует ли легаси-аккаунт Cloud Build · 2026-08-18

**Объект замера определён:** проект GCP `project-c451b48a-07ae-4de4-961` (`11_INFRA_FACTS.md`,
раздел «GCP», строка `PROJECT_ID`) и три сервисных аккаунта в нём — существовали до этой сессии.
Предмет раунда 2 — принципал `450925595005@cloudbuild.gserviceaccount.com`, названный значением
правила в `ADR-076` п.3.

**Роль и мандат:** архитектор, класс A — только чтение облака (`describe`/`list`/`get-iam-policy`).
Ни одной операции записи в GCP этой сессией не исполнено.
**Коммит на входе:** `419955300a570537284aa8f28a8d16e14645bebe`, дерево чистое.

**Предыдущий раунд:** `reference/T-1-0_build_sa_measurement_2026-08-18.md` и `ADR-076`.
Решение не переисследуется — продолжается: раунд 1 установил ПРИЧИНУ отказа сборки,
раунд 2 проверяет ЗНАЧЕНИЕ, которым раунд 1 эту причину закрывал.

---

## 1. Отказ раунда 2 — новое место, не сборка

`bash scripts/T-1-0_deploy.sh part1` с флагом по `ADR-076` п.3 упал ДО Cloud Build, на валидации
самого флага:

```
ERROR: (gcloud.functions.deploy) ResponseError: status=[400], code=[],
message=[projects/-/serviceAccounts/450925595005@cloudbuild.gserviceaccount.com
should be a valid email or unique id.]
```

Вопрос замера: у исполняющей identity нет права РЕЗОЛВИТЬ этот аккаунт, или аккаунта нет как
ресурса. Различающая проверка — сравнение того же вызова на заведомо существующих аккаунтах.

## 2. Замер 1 — три `describe` одной командой, из них два обратными контролями

```
$ gcloud iam service-accounts describe lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com \
    --project=project-c451b48a-07ae-4de4-961 --format="value(email,uniqueId,disabled)"
lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com	106012128270313074763

$ gcloud iam service-accounts describe 450925595005-compute@developer.gserviceaccount.com \
    --project=project-c451b48a-07ae-4de4-961 --format="value(email,uniqueId,disabled)"
450925595005-compute@developer.gserviceaccount.com	117487850137503817821

$ gcloud iam service-accounts describe 450925595005@cloudbuild.gserviceaccount.com \
    --project=project-c451b48a-07ae-4de4-961 --format="value(email,uniqueId)"
ERROR: (gcloud.iam.service-accounts.describe) PERMISSION_DENIED: Permission
'iam.serviceAccounts.get' denied on resource
'//iam.googleapis.com/projects/-/serviceAccounts/111318223703349525203' (or it may not exist).
... authenticated as ilyasbazarov4@gmail.com
```

**Тот же вызов, та же identity, тот же проект: два аккаунта читаются, третий — нет.** Отказ не
может быть свойством права: право `iam.serviceAccounts.get` у identity в этом проекте есть и
предъявлено дважды. Отказ есть свойство самого ресурса.

## 3. Замер 2 — право `actAs`/`get` у исполняющей identity, прямо из состава роли

```
$ gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 --flatten="bindings[].members" \
    --format="value(bindings.role)" --filter="bindings.members:user:ilyasbazarov4@gmail.com"
roles/owner
roles/resourcemanager.projectMover

$ gcloud iam roles describe roles/owner --format="value(includedPermissions)" \
    | tr ';' '\n' | grep -nE "iam\.serviceAccounts\.(actAs|get)$"
9376:iam.serviceAccounts.actAs
9383:iam.serviceAccounts.get
```

Обратный контроль исправности `grep` — заведомо посторонняя строка в том же выводе даёт `0`
совпадений (`grep -c "zzz.nonexistent.permission"` → `0`), то есть две строки выше не артефакт.

**Вывод: IAM-правка ДЛЯ `ilyasbazarov4@gmail.com` не требуется вовсе.** `roles/owner` уже несёт и
`iam.serviceAccounts.get`, и `iam.serviceAccounts.actAs`. Гипотеза «человеческой identity не хватает
права на легаси-аккаунт» замером ОТВЕРГНУТА.

## 4. Замер 3 — аккаунта нет в проекте

```
$ gcloud iam service-accounts list --project=project-c451b48a-07ae-4de4-961
DISPLAY NAME                        EMAIL                                                                    DISABLED
Default compute service account     450925595005-compute@developer.gserviceaccount.com                       False
App Engine default service account  project-c451b48a-07ae-4de4-961@appspot.gserviceaccount.com               False
lombard-pipeline                    lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com  False
```

Три аккаунта, `450925595005@cloudbuild.gserviceaccount.com` среди них НЕТ — и не было в раунде 1
(тот же вывод, замер 1 предыдущего файла). Раунд 1 прочитал этот вывод и не сделал из него
вывода: значение `ADR-076` п.3 выбрано по наличию РОЛИ в политике, а не по наличию АККАУНТА
в проекте.

```
$ gcloud projects describe project-c451b48a-07ae-4de4-961 --format="yaml(projectNumber,createTime)"
createTime: '2026-06-24T09:18:14.863Z'
projectNumber: '450925595005'
```

Проект заведён 2026-06-24.

## 5. Замер 4 — биндинг существует, принципал не существует: это НЕ противоречие

```
$ gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 --flatten="bindings[].members" \
    --format="value(bindings.members,bindings.role)" | sort -u
serviceAccount:450925595005@cloudbuild.gserviceaccount.com	roles/cloudbuild.builds.builder
serviceAccount:lombard-pipeline@…iam.gserviceaccount.com	roles/secretmanager.secretAccessor
serviceAccount:service-450925595005@containerregistry.iam.gserviceaccount.com	roles/containerregistry.ServiceAgent
serviceAccount:service-450925595005@gcf-admin-robot.iam.gserviceaccount.com	roles/cloudfunctions.serviceAgent
serviceAccount:service-450925595005@gcp-sa-artifactregistry.iam.gserviceaccount.com	roles/artifactregistry.serviceAgent
serviceAccount:service-450925595005@gcp-sa-cloudbuild.iam.gserviceaccount.com	roles/cloudbuild.serviceAgent
serviceAccount:service-450925595005@gcp-sa-cloudscheduler.iam.gserviceaccount.com	roles/cloudscheduler.serviceAgent
serviceAccount:service-450925595005@gcp-sa-pubsub.iam.gserviceaccount.com	roles/pubsub.serviceAgent
serviceAccount:service-450925595005@serverless-robot-prod.iam.gserviceaccount.com	roles/run.serviceAgent
user:ilyasbazarov4@gmail.com	roles/owner
user:ilyasbazarov4@gmail.com	roles/resourcemanager.projectMover
user:omegalombard2023@gmail.com	roles/owner
```

Строка политики есть; аккаунта в проекте нет (замер 3); `describe` его не резолвит при наличии
права (замеры 1–2). **Политика IAM хранит член биндинга как строку и существования принципала не
гарантирует.** Наличие роли у имени не есть наличие аккаунта с этим именем — ровно эта подмена
и стоила раунда.

## 6. Замер 5 — РЕШАЮЩИЙ для выбора пути: билд-разрешений нет НИ У ОДНОГО существующего аккаунта

```
$ for sa in 450925595005-compute@developer.gserviceaccount.com \
            project-c451b48a-07ae-4de4-961@appspot.gserviceaccount.com \
            lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com; do
    gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 --flatten="bindings[].members" \
      --format="value(bindings.role)" --filter="bindings.members:$sa"; done
--- 450925595005-compute@developer.gserviceaccount.com ---
<пусто>
--- project-c451b48a-07ae-4de4-961@appspot.gserviceaccount.com ---
<пусто>
--- lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com ---
roles/secretmanager.secretAccessor
```

Исправность фильтра подтверждена замером 4: тот же вызов без фильтра печатает 12 строк.

**Следствие, снимающее вопрос запуска «есть ли путь без IAM-правки»: пути без IAM-правки НЕТ.**
Сборка исполняется сервисным аккаунтом; в проекте существуют ровно три, и ни один не несёт
билд-разрешений. Явный `--build-service-account` необходимость IAM-правки не создаёт и не
отменяет — он выбирает, КОМУ она достанется. Отказ от флага (путь «выдать роль дефолтному compute
SA») — та же самая правка, только на аккаунте, который организация клиента намеренно держит
бесправным.

## 7. Замер 6 — политики, ограничивающие выбор

```
$ gcloud resource-manager org-policies describe \
    constraints/iam.automaticIamGrantsForDefaultServiceAccounts \
    --project=project-c451b48a-07ae-4de4-961 --effective
booleanPolicy:
  enforced: true

$ gcloud resource-manager org-policies describe constraints/iam.disableServiceAccountCreation \
    --project=project-c451b48a-07ae-4de4-961 --effective
booleanPolicy: {}
```

Первая действует (подтверждение `ADR-076` п.1, значение не изменилось), вторая — нет и служит
обратным контролем исправности вызова. **Заведение нового сервисного аккаунта организацией
не запрещено.**

## 8. Замер 7 — состояние ресурса и сборок на входе раунда 2

```
$ gcloud functions list --project=project-c451b48a-07ae-4de4-961
NAME      STATE   TRIGGER       REGION        ENVIRONMENT
cf-daily  FAILED  HTTP Trigger  europe-west3  2nd gen

$ gcloud builds list --region=europe-west3 --project=project-c451b48a-07ae-4de4-961 --limit=5
ID                                    CREATE_TIME                STATUS
3b095e85-6052-4f39-afeb-829aa19a6e5c  2026-08-18T10:27:22+00:00  FAILURE
```

**Расхождение текста запуска с замером названо поимённо (`ADR-027`).** Текст сессии утверждал:
«cf-daily в GCP не создан ни разу — откат не требуется, объект чистый на старте». `functions list`
печатает `cf-daily` в состоянии `FAILED`. Огрызок существует, откат требуется, `ADR-076` п.6
остаётся в силе. Принять утверждение запуска означало бы деплоить поверх сломанного объекта,
не назвав этого.

Сборка ровно одна и та же, что в раунде 1 — второй попытки сборки не было. Это независимо
подтверждает, что отказ раунда 2 произошёл на валидации флага, ДО Cloud Build.

## 9. Что НЕ измерено и угадыванию не подлежит

1. Пройдёт ли сборка целиком под новым выделенным билд-аккаунтом с `roles/cloudbuild.builds.builder`.
   Различающая проверка ровно одна — фактический деплой (класс B). Отказ там → стоп и вопрос
   владельцу, а не третий аккаунт наугад.
2. Требует ли платформа дополнительного биндинга сервисному агенту Cloud Build на новый
   билд-аккаунт. Читаемым способом это не устанавливается; проявится тем же деплоем.
3. Пропустит ли орг-политика РУЧНУЮ выдачу роли дефолтному compute SA. Не измерено намеренно:
   выбранный путь дефолтных аккаунтов не касается вовсе, и вопрос на него не влияет.

## 10. Классификация (полный разбор — `ADR-077`)

Строкой в `07_GAPS.md` раунд 2 не заводится по тем же трём основаниям, что раунд 1 (`ADR-076`
п.1): неопределённого объекта (`ADR-061`) нет — объект платформенный, определён и измерен;
недостающего у владельца знания не осталось; остаток — одно действие класса B, чей носитель
карточка подтверждения, а не реестр вопросов.
