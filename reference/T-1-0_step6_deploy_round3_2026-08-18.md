# ИСПОЛНЕНИЕ · T-1-0 шаг 6 · раунд 3 · деплой `cf-daily` · 2026-08-18

**Класс B, карточка подтверждена владельцем.** Основание — карточка шага 6 (что исполняется,
объект, откат) после закрытия шага 6-Б. Исполнено сессией архитектора под
`ilyasbazarov4@gmail.com`. **Коммит на входе:** `141c0ed`.

---

## 1. Главный факт раунда: СБОРКА ПРОШЛА

```
$ bash scripts/T-1-0_deploy.sh part1
=== Часть 1 (шаг 6): деплой Cloud Function cf-daily ===
Preparing function...done.
Deploying function...
[Build]……done
[Service]……failed
Failed.
```

```
$ gcloud builds list --region=europe-west3 --project=project-c451b48a-07ae-4de4-961 --limit=3
ID                                    CREATE_TIME                STATUS
037cf149-b15a-4ecb-9508-f20e89964f92  2026-08-18T11:25:55+00:00  SUCCESS
3b095e85-6052-4f39-afeb-829aa19a6e5c  2026-08-18T10:27:22+00:00  FAILURE

$ gcloud builds describe 037cf149-b15a-4ecb-9508-f20e89964f92 --region=europe-west3 \
    --project=project-c451b48a-07ae-4de4-961 --format="value(serviceAccount,status)"
projects/project-c451b48a-07ae-4de4-961/serviceAccounts/lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com	SUCCESS
```

**Вопрос, стоивший двух раундов, закрыт положительным фактом:** платформа приняла выделенный
билд-аккаунт, сборка отработала целиком под ним. Пункт «не измерено» `ADR-077` снят —
`ADR-076` п.2 (называть билд-аккаунт явно) и `ADR-077` п.5 (значение `lombard-build`)
подтверждены исполнением, а не рассуждением. Прежняя сборка под дефолтным compute SA в том же
листинге осталась `FAILURE` — контраст предъявлен одной командой.

## 2. Отказ переехал на следующий этап и сменил класс

```
ERROR: (gcloud.functions.deploy) OperationError: code=3, message=Could not create or update
Cloud Run service cf-daily, Container Healthcheck failed. Revision 'cf-daily-00001-fav' is not
ready and cannot serve traffic. The user-provided container failed to start and listen on the
port defined provided by the PORT=8080 environment variable within the allocated timeout.
```

`[Build] done` · `[Service] failed` — граница названа платформой сама: собранный контейнер
не стартует. Это уже не инфраструктура клиента и не IAM, а наш код.

## 3. Причина установлена целиком — одна строка нашего исходника

```
$ gcloud logging read 'resource.type="cloud_run_revision" AND
    resource.labels.service_name="cf-daily"' --project=project-c451b48a-07ae-4de4-961 --limit=40
… File "/workspace/main.py", line 30, in <module>
    from functions.cf_daily import bq_loader, status, telegram_send
ModuleNotFoundError: No module named 'functions'
Container called exit(1).
Default STARTUP TCP probe failed 1 time consecutively for container "worker" on port 8080.
```

Круг замкнут без остатка: `--source=functions/cf_daily` кладёт в контейнер СОДЕРЖИМОЕ каталога,
корнем `/workspace`. В контейнере `main.py`, `bq_loader.py`, `status.py`, `telegram_send.py` —
соседи верхнего уровня, пакета `functions` нет вовсе. Импорт, законный от корня репозитория,
в контейнере неразрешим по построению.

## 4. Почему зелёные локальные тесты этого не поймали, и это НЕ упрёк тестам

```
$ grep -rn "^from functions\|from functions\.cf_daily" functions/cf_daily/*.py
functions/cf_daily/main.py:30:from functions.cf_daily import bq_loader, status, telegram_send
functions/cf_daily/test_bq_loader.py:17:from functions.cf_daily.bq_loader import (
functions/cf_daily/test_status.py:16:from functions.cf_daily.status import (
functions/cf_daily/test_telegram_send.py:18:from functions.cf_daily.telegram_send import TelegramSendError, send_message
functions/cf_daily/test_main.py:17:from functions.cf_daily.main import (
```

Тесты запускаются от корня репозитория и импортируют ровно тем же путём, что `main.py`.
**Они проверяют код в упаковке, которой в проде не существует, и зелёными будут всегда** —
дефект лежит не в логике, а в расхождении корня импорта между тестом и контейнером. Ни один
тест такой формы его поймать не может: он воспроизводит саму ошибку, а не проверяет её.

## 5. Откат карточки исполнен

```
$ gcloud functions delete cf-daily --region=europe-west3 \
    --project=project-c451b48a-07ae-4de4-961 --quiet
Deleted [projects/project-c451b48a-07ae-4de4-961/locations/europe-west3/functions/cf-daily].

$ gcloud functions list --project=project-c451b48a-07ae-4de4-961
Listed 0 items.
```

Огрызок `FAILED` не оставлен: откат — часть подтверждённой карточки, а не новое действие.
В облаке чисто, следующий деплой пойдёт созданием с нуля.

## 6. Что этим установлено и что осталось

**Установлено:** билд-аккаунт `lombard-build` работает (сборка `SUCCESS`); причина отказа
раунда 3 — дефект упаковки исходника в нашем коде, класс A, целиком внутри
`functions/cf_daily/`.
**Не установлено:** пройдёт ли контейнер healthcheck после исправления импортов и отработает
ли нитка (а)–(е) на живых данных. Различающая проверка — тот же деплой после шага 6-Г.
