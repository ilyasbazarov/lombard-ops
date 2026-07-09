# 02 · DATA_CONTRACTS — Схемы и контракты данных

**Версия:** 0.9 · **Статус:** SEMI-STABLE · **обновлено:** 2026-07-10
§1–2 согласованы (из ТЗ). §3 заполняется по итогам дискавери БД (T-0-2/T-0-3) — до этого пуст, не выдумывать.

## 1. Источник: Firebird / PawnShop — известные факты

- СУБД: **Firebird 2.5.9**, порт **3057** (нестандартный), кодировка **UTF-8**.
- Документации схемы нет; описания таблиц — в поле description метаданных, на русском.
- Начисления (%/пени) в БД **не хранятся** — вычисляет приложение (→ ADR-006).
- Продление займа: два механизма — операция «Погашение» и «Переоткрытие договора»; связь со старым договором пишется в поле «Примечание». Табличное устройство — выяснить (T-0-4).
- Структура меняется при обновлениях без уведомления (→ guard, ADR-004).
- Прод-доступ: отдельный **read-only пользователь** (T-0-5). Дискавери — под админом, дисциплина «только SELECT».

## 2. BigQuery: датасет `lombard_ops`

DDL — источник истины в `/sql/ddl/`. Ключевые контракты:

| Таблица | Ключевые поля | Контракт |
|---|---|---|
| `loans_raw` | contract_id, vehicle_id (VIN), client_name, vehicle_make, vehicle_model, vehicle_year, loan_amount, issue_date, due_date, status_raw, renewed, renewed_date, loaded_at | staging; пишет только connector |
| `events` | event_id, timestamp, contract_id, vehicle_id, event_type, payload JSON, actor, idempotency_key | **APPEND ONLY, никогда не обновляется.** PARTITION BY DATE(timestamp), CLUSTER BY contract_id |
| `offers` | offer_id, contract_id, vehicle_id, offer_date, buyer_contact, offer_amount, vs_floor, decision, decided_by, decided_at, tg_message_id | append only |
| `pricing_snapshots` | contract_id, calc_date, balance_amount, realization_price, floor_price, floor_pct, depreciation_coeff, days_since_default | снапшот в день на займ в 🔴 |
| `vehicle_catalog` | make, model, liquidity_class, ltv_max, buyout_price, updated_at | справочник ликвидности; редактируется через /catalog |
| `assessments` | assessment_id, contract_id, vehicle_id, make, model, vin, year, mileage, *_discount, total_discount, base_price, max_loan, photos_gcs_path, assessor, created_at | результат формы осмотра |

`event_type` enum: IMPORT, ASSESSMENT, STATUS_CHANGE, ALERT_SENT, OFFER_RECEIVED, DECISION_MADE, PRE_MARKETING_START, REALIZATION_START.

Идемпотентность алертов: `idempotency_key = contract_id + event_type + date`; перед отправкой — EXISTS-проверка в `events`.

## 3. Маппинг PawnShop → canonical ⏳

Заполняется после T-0-2 (структура БД) и T-0-3 (маппинг). Формат:

| Canonical поле | Таблица.колонка Firebird | Тип | Преобразование | Примечание |
|---|---|---|---|---|
| contract_id | ⏳ | | | |
| vehicle_id (VIN) | ⏳ | | нормализация: strip, upper, без пробелов/дефисов | суррогат при отсутствии: `VEH-{YYYYMMDD}-{госномер}`, флаг no_vin |
| issue_date / due_date | ⏳ | | | |
| loan_amount | ⏳ | | | |
| rate / пени-правила | ⏳ | | | нужны для balance_amount (ADR-006) |
| renewals-механизм | ⏳ | | | T-0-4 |

Правило: канонизация — единственное место преобразований; ниже по конвейеру данные уже чистые.

## 4. Конфиги (GCS `${PROJECT_ID}-config`)

- `mapping.json` — маппинг §3 + эталон отпечатка схемы Firebird (guard).
- `config.json` — бизнес-пороги: alert_days, floor_pct по классам, depreciation_per_10_days, staleness_threshold_hours, chat_id участников. Панель управления Исы: правка файла = смена правил без деплоя.
