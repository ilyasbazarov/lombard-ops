# 01 · ARCHITECTURE — Компоненты и потоки

**Версия:** 0.9 · **Статус:** SEMI-STABLE · **обновлено:** 2026-07-10
Открытые пункты помечены `⏳` и привязаны к задачам `04_ROADMAP`.

## 1. Общая схема

```
ERP-сервер клиента (Windows Server, Firebird 2.5.9 · БД PawnShop)
        │  read-only SELECT (⏳ канал: WG-туннель ИЛИ агент, ADR pending, T-0-8)
        ▼
[connector]  Cloud Run Job, по расписанию ──► BigQuery: staging (loans_raw и сырьё)
        ▼
[canonical]  SQL-слой канонизации ──► BigQuery: canonical view + справочники
        ▼
[cf-daily]   Cloud Function, Cloud Scheduler 08:00 Asia/Bishkek
             статусы → алерты → идемпотентность → pricing → сводка 09:05
        ├──► Telegram Bot API (push Исе/Бектуру/Эльхану)
        └──► BigQuery: events (append-only), pricing_snapshots
[cf-tg-handler]  Cloud Function, webhook Telegram — кнопки «ниже floor»
[app-lombard]    Cloud Run: React + API в одном сервисе, за Identity Platform
                 экраны: реестр · карточка займа (?id=) · форма осмотра · /catalog · /offer
[GCS]            фото залогов photos/{VIN}/{timestamp}/ · конфиги · cfsource
[Secret Manager] telegram-bot-token · креды read-only пользователя Firebird · chat_id
```

## 2. Компоненты

| Компонент | Технология | Назначение |
|---|---|---|
| `job-connector` | Cloud Run Job (Python) | Подключение к Firebird → guard схемы → выгрузка нужных таблиц → BigQuery staging |
| `cf-daily` | Cloud Function (Python), Scheduler 08:00 | Конвейер шагов: canonical → renewals → staleness → статусы → дедупликация → алерты → pricing → сводка. Упал ранний шаг — поздние не выполняются |
| `cf-tg-handler` | Cloud Function (Python), HTTP webhook | Обработка inline-кнопок Telegram (решения по floor), редактирование сообщений, запись в `offers`/`events` |
| `app-lombard` | Cloud Run (React + API) | Все экраны для людей. Auth: Identity Platform (email+пароль), роли в custom claims: `owner`/`manager`/`assessor`. API проверяет токен и роль на каждом запросе |
| BigQuery `lombard_ops` | датасет | Таблицы — `02_DATA_CONTRACTS` |
| GCS | бакеты `${PROJECT_ID}-{photos,config,cfsource}` | Фото, конфиги, исходники деплоя |

## 3. Guard схемы Firebird (ADR-004)

Вендор меняет структуру БД без уведомления. Защита:

1. Перед каждым чтением connector снимает отпечаток метаданных используемых таблиц (RDB$-системные таблицы: колонки, типы) и сверяет с эталоном в конфиге.
2. Расхождение → **стоп + алерт всем**, чтение не выполняется.
3. В запросах — только явные списки колонок, `SELECT *` запрещён.
4. Обновление эталона — осознанное действие через правку конфига (после разбора, что изменилось).

## 4. Сетевой доступ к ERP ⏳ (T-0-8, ADR pending)

Факты: белый (возможно динамический) IP, DDNS, Keenetic с WG-сервером, порт Firebird открыт для LAN+VPN-подсетей. Кандидаты для прода:

- **A. WG-туннель из GCP** — connector ходит в БД напрямую. Плюс: нулевой софт на сервере. Минус: связность GCP↔Keenetic, точка отказа — туннель.
- **B. Агент на сервере** — служба с только исходящим трафиком пушит выгрузку в GCS; дальше конвейер как есть. Плюс: не нужен inbound вообще. Минус: софт на машине клиента.
- Запасной канал: штатная «выгрузка в бух. программы» PawnShop.

Решение — по результатам проб, отдельным ADR.

## 5. Балансовая стоимость вычисляется у нас (ADR-006)

Начисления (%/пени) в БД PawnShop не хранятся — считает приложение вендора. `balance_amount` вычисляем сами из условий договора (ставка, сроки — маппинг в `02`) по формулам `03_BUSINESS_SPEC §4`. Дискавери обязан найти поля условий договора.

## 6. Триггеры пересмотра архитектуры

| Триггер | Что пересматривать |
|---|---|
| >250–300 активных займов | Ресурсы Cloud Run / структура запросов BQ |
| Второй филиал | Multi-tenant: `branch_id` в схеме + отдельные Telegram-чаты |
| cf-daily упирается в timeout | Разбить на функции с Pub/Sub-оркестрацией |
| Потребность в ML | Vertex AI поверх BigQuery, основной контур не меняется |
