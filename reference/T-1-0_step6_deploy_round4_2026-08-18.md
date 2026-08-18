# ИСПОЛНЕНИЕ · T-1-0 шаг 6 · раунд 4 (финальный) · деплой `cf-daily` УСПЕШЕН · 2026-08-18

**Класс B, карточка подтверждена владельцем.** Текст карточки — тот же, что раунда 3; значение
флага `--build-service-account` не менялось. Основание причины, устранённой шагом 6-Г, —
`ADR-078`, коммит исполнителя `5f79809`. **Коммит на входе:** `5f79809`.

---

## 1. Деплой

```
$ bash scripts/T-1-0_deploy.sh part1
=== Часть 1 (шаг 6): деплой Cloud Function cf-daily ===
…
state: ACTIVE
url: https://europe-west3-project-c451b48a-07ae-4de4-961.cloudfunctions.net/cf-daily
uri: https://cf-daily-ixy63xgujq-ey.a.run.app
revision: cf-daily-00001-vap
serviceAccountEmail: lombard-pipeline@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
buildConfig.serviceAccount: projects/project-c451b48a-07ae-4de4-961/serviceAccounts/lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
```

## 2. Независимая приёмка отдельным вызовом (не тем же, что печатал деплой)

```
$ gcloud functions describe cf-daily --region=europe-west3 --gen2 \
    --project=project-c451b48a-07ae-4de4-961 \
    --format="value(state,serviceConfig.uri,buildConfig.serviceAccount)"
ACTIVE	https://cf-daily-ixy63xgujq-ey.a.run.app	projects/project-c451b48a-07ae-4de4-961/serviceAccounts/lombard-build@project-c451b48a-07ae-4de4-961.iam.gserviceaccount.com
```

**Оба вопроса, стоившие трёх раундов, закрыты положительным фактом одновременно:** билд-аккаунт
`lombard-build` — сборка и весь деплой; контейнер стартует — `state: ACTIVE`, ревизия принимает
трафик. `ADR-076`/`ADR-077`/`ADR-078` не оставляют пунктов «не измерено» по билд-аккаунту и
упаковке. Шаг 6 брифа `T-1-0` — **закрыт**.

## 3. Что этим НЕ установлено

Работоспособность самой нитки (а)–(е) на живых данных (листинг бакета, загрузка в BQ, расчёт
статуса, отправка в Telegram) — HTTP-триггер ещё не вызывался. Это шаги 7–9 брифа, отдельные
карточки подтверждения.
