# ИСПОЛНЕНИЕ · T-1-0 шаг 6-Б · билд-аккаунт `lombard-build` · 2026-08-18

**Класс B, карточка подтверждена владельцем.** Основание — `ADR-077` п.9 (текст карточки, откат,
приёмка). Первые три команды исполнены владельцем в Cloud Shell под `ilyasbazarov4@gmail.com`,
приёмка и повтор третьей команды — сессией архитектора под той же учётной записью.
**Коммит на входе:** `e3dacc5`.

---

## 1. Команда 1 — удаление огрызка (откат предыдущего раунда)

```
$ gcloud functions delete cf-daily --region=europe-west3 \
    --project=project-c451b48a-07ae-4de4-961 --quiet
Preparing function...done.
Deleting function...
  [Artifact Registry]done
  [Service]done
Done.
Deleted [projects/project-c451b48a-07ae-4de4-961/locations/europe-west3/functions/cf-daily].
```

Приёмка — объект исчез, а не «команда вернула ноль»:

```
$ gcloud functions list --project=project-c451b48a-07ae-4de4-961
Listed 0 items.
```

## 2. Команда 2 — заведение билд-аккаунта

```
$ gcloud iam service-accounts create lombard-build \
    --display-name="lombard-build (билд-аккаунт деплоя облачного кода, ADR-077)" \
    --project=project-c451b48a-07ae-4de4-961
Created service account [lombard-build].
```

## 3. Команда 3 — ОТКАЗ на первом исполнении, и это новый факт

```
$ gcloud projects add-iam-policy-binding project-c451b48a-07ae-4de4-961 \
    --member=serviceAccount:lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com \
    --role=roles/cloudbuild.builds.builder
ERROR: Policy modification failed. For a binding with condition, run
"gcloud alpha iam policies lint-condition" to identify issues in condition.
ERROR: (gcloud.projects.add-iam-policy-binding) INVALID_ARGUMENT:
Service account lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com does not exist.
```

**Текст отказа буквально совпадает с диагнозом раунда 2 («аккаунта не существует») и означает
ПРОТИВОПОЛОЖНОЕ.** Различающая проверка — та самая, что назначена `ADR-077` п.2, и она отделила
один случай от другого за одну команду:

```
$ gcloud iam service-accounts describe \
    lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com \
    --project=project-c451b48a-07ae-4de4-961 --format="value(email,uniqueId,disabled)"
lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com	115827718002622110291
```

Аккаунт существует, `uniqueId` непустой, не отключён. Значит отказ команды 3 — **окно
распространения нового принципала между IAM и Resource Manager**, а не отсутствие объекта.
Отличие от случая `ADR-077`: там `describe` отказывал, здесь `describe` отвечает.

## 4. Команда 3 — повтор, успех

Повтор той же команды той же карточки (новое действие не заводится: команда, объект, откат
и подтверждение — те же):

```
$ gcloud projects add-iam-policy-binding project-c451b48a-07ae-4de4-961 \
    --member=serviceAccount:lombard-build@…iam.gserviceaccount.com \
    --role=roles/cloudbuild.builds.builder
… etag: BwZZUG8JJkc=
  version: 1
```

## 5. Приёмка шага 6-Б целиком

```
$ gcloud projects get-iam-policy project-c451b48a-07ae-4de4-961 \
    --flatten="bindings[].members" --format="value(bindings.role)" \
    --filter="bindings.members:lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com"
roles/cloudbuild.builds.builder
```

До правки тот же фильтр давал пустой вывод (замер §3 выше по времени). Исправность фильтра
подтверждена обратным запросом: тот же вызов без фильтра печатает **12** уникальных членов
политики против 11 до правки — прирост ровно на заведённый аккаунт.

**Три условия приёмки выполнены: огрызка нет, аккаунт есть с непустым `uniqueId`, роль на нём
предъявлена строкой политики.** Шаг 6-Б закрыт.

## 6. Что этим НЕ установлено

Пройдёт ли сборка `cf-daily` под `lombard-build` целиком — по-прежнему не измерено. Различающая
проверка одна: деплой шага 6-В (класс B). Потолок `ADR-077` п.11 в силе — отказ там закрывается
строкой `07_GAPS.md`, а не четвёртым аккаунтом.
