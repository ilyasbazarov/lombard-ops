# 02 · DATA_CONTRACTS — Схемы и контракты данных

**Версия:** 0.9 · **Статус:** SEMI-STABLE · **обновлено:** 2026-07-10
§1–2 согласованы (из ТЗ). §3 заполняется по итогам дискавери БД (T-0-2/T-0-3) — до этого пуст, не выдумывать.

## 1. Источник: Firebird / PawnShop — известные факты

- СУБД: **Firebird 2.5.9**, порт **3057** (нестандартный), кодировка **UTF-8**.
- Документации схемы нет; описания таблиц — в поле description метаданных, на русском.
- **Параметры** начислений (%/пеня/хранение/страховка, правила и флаги) в БД **хранятся** — таблица `CONTRACTS_TERMS`, 28 колонок, строка на договор (замер 2026-08-12). Снапшот **вычисленной суммы** на произвольную дату не хранится — её считает приложение (→ ADR-006, обоснование исправлено ADR-045). Разнесение фактических платежей по компонентам — предмет замера `OPERATIONS`, не измерено.
- Продление займа: два механизма — операция «Погашение» и «Переоткрытие договора»; связь со старым договором пишется в поле «Примечание». Табличное устройство — выяснить (T-0-4).
- Структура меняется при обновлениях без уведомления (→ guard, ADR-004).
- Прод-доступ: отдельный пользователь, **собственные права которого — только SELECT** на используемые таблицы (T-0-5). Дискавери — под админом, дисциплина «только SELECT».
- **Гранты этого пользователя read-only НЕ гарантируют** (измерено T-0-5, 2026-08-11): псевдо-пользователь `PUBLIC` несёт полный набор прав на используемых таблицах, и отзывать их мы не будем (ADR-032). Контроль записи поэтому лежит на производителе данных и построен слоями (ADR-033): **основной — единственная точка доступа с белым списком операторов**, на сервер не уходит ничего, кроме SELECT/WITH-выборки и чтения системных RDB$/MON$; **эшелон — транзакция только на чтение** при каждом подключении, она остаётся обязательной и **с 2026-08-12 называется механизмом, отбивающим запись на стороне сервера: замер T-0-17 на нашем экземпляре 2.5.9 предъявил отказ `SQLSTATE = 42000` `attempted update during read-only transaction`** (ADR-037). Граница действия названа: отказ приходит на уровне ЗАДЕВАЕМОЙ ЗАПИСИ — оператор, не задевающий ни одной строки, проходит молча, поэтому пробой режима он не является. Эшелон закрывает нашу ошибку, а не стороннего клиента: тот транзакцию только на чтение не откроет вовсе.

## 2. BigQuery: датасет `lombard_ops`

DDL — источник истины в `/sql/ddl/`. Ключевые контракты:

| Таблица | Ключевые поля | Контракт |
|---|---|---|
| `loans_raw` | contract_id, vehicle_id (VIN), client_name, vehicle_make, vehicle_model, vehicle_year, loan_amount, issue_date, due_date, status_raw, renewed, renewed_date, loaded_at | staging; пишет только connector |
| `events` | event_id, timestamp, contract_id, vehicle_id, event_type, payload JSON, actor, idempotency_key | **APPEND ONLY, никогда не обновляется.** PARTITION BY DATE(timestamp), CLUSTER BY contract_id |
| `offers` | offer_id, contract_id, vehicle_id, offer_date, buyer_contact, offer_amount, vs_floor, decision, decided_by, decided_at, tg_message_id | append only |
| `pricing_snapshots` | contract_id, calc_date, balance_amount, realization_price, floor_price, floor_pct, depreciation_coeff, days_since_default | снапшот в день на займ в 🔴 |
| `vehicle_catalog` | make, model, liquidity_class, ltv_max, buyout_price, comment, updated_at | справочник ликвидности. **Источник и место ведения — лист «Справочник»** (`ADR-060`), эта таблица — рабочая копия: пишет её импорт `tools/catalog_import.py`, экран `/catalog` в v1 только читает. Производная `LTV × скупочная база` НЕ хранится — считается (принцип 1) |
| `assessments` | assessment_id, contract_id, vehicle_id, make, model, vin, year, mileage, total_discount, base_price, max_loan, photos_gcs_path, assessor, created_at **+ набор применённых факторов записью** (идентификатор фактора, значение, применённый вес) | результат формы осмотра. **Wildcard `*_discount` снят `ADR-058`:** фиксированных колонок по факторам не будет — факторы живут настраиваемым справочником, поэтому перечня колонок не существует в принципе. Физический вид набора (вложенная запись, отдельная таблица, JSON) выбирает `T-2-0` |

`event_type` enum: IMPORT, ASSESSMENT, STATUS_CHANGE, ALERT_SENT, OFFER_RECEIVED, DECISION_MADE, PRE_MARKETING_START, REALIZATION_START.

Идемпотентность алертов: `idempotency_key = contract_id + event_type + date`; перед отправкой — EXISTS-проверка в `events`.

## 3. Маппинг PawnShop → canonical

Заполняется после T-0-2 (структура БД) и T-0-3 (маппинг); поля начисления — по T-0-3b
(`reference/T-0-3b_accrual_params_measurement_2026-08-12.md`). Формат:

| Canonical поле | Таблица.колонка Firebird | Тип | Преобразование | Примечание |
|---|---|---|---|---|
| contract_id | `CONTRACTS.CONTRACT_ID` | INTEGER | — | |
| contract_num | `CONTRACTS.CONTRACT_NUM` | VARCHAR(320) | — | номер договора, не суррогат |
| vehicle_id (VIN) | ⏳ | | нормализация: strip, upper, без пробелов/дефисов | суррогат при отсутствии: `VEH-{YYYYMMDD}-{госномер}`, флаг no_vin — вне scope T-0-3b |
| issue_date | `CONTRACTS.CONTRACT_DATE` | DATE | — | дата выдачи; НЕ отражает дату последнего продления (`ADR-010 v3` последствие, `T-0-3b`) |
| due_date (плановое) | `CONTRACTS.PLAN_CLOSE_DATE` | DATE | — | «от последней операции» — переживает продления, в отличие от `issue_date` |
| loan_amount | `CONTRACTS.DEPOSIT_SUM` | NUMERIC(scale -2) | ÷100 → главная единица | коп.; на снятых договорах числовое значение практически совпадает с $ на экране вендора — требует отдельного подтверждения валюты, не факт |
| rate (проценты) | `CONTRACTS_TERMS.DEPOSIT_PERC` | NUMERIC(scale -5) | месячная ставка, % | день-каунт от `issue_date` НЕ подтверждён оракулом — `T-0-3b_oracle_reconciliation_2026-08-12.md` |
| пени-правила | `CONTRACTS_TERMS.PENALTY_PERC`, `PENALTY_DAYS`, `IS_PENAL_FROM_RET_SUM` | см. измерение | | точка отсчёта просрочки и механика разового штрафа — не подтверждены оракулом, два кандидата в измерении |
| хранение (STORAGE) | `CONTRACTS_TERMS.STORAGE_TYPE`, `STORAGE_VAL`, `STORAGE_MIN_DAYS`, `IS_STORAGE_STOP_W_PEN` | см. измерение | | компонента `ADR-010 v3`; период начисления НЕ выбран — два кандидата, оракул не сошёлся |
| страховка (INSURE) | `CONTRACTS_TERMS.INSURE_TYPE`, `INSURE_VAL`, `INSURE_MIN_DAYS` | см. измерение | | на замеренных 98 активных договорах — везде ноль (`INSURE_VAL=0`) |
| renewals-механизм | ⏳ | | | T-0-4; блокирует финализацию `issue_date`/`rate`-формулы — см. вывод `T-0-3b_oracle_reconciliation_2026-08-12.md` |

Правило: канонизация — единственное место преобразований; ниже по конвейеру данные уже чистые.

## 4. Конфиги (GCS `${PROJECT_ID}-config`)

- `mapping.json` — маппинг §3 + эталон отпечатка схемы Firebird (guard).
- `config.json` — бизнес-пороги: alert_days, floor_pct по классам, depreciation_per_10_days, staleness_threshold_hours, chat_id участников. Панель управления Исы: правка файла = смена правил без деплоя. **Значения объявлены боевыми `ADR-057`** (дефолты `03 §1` и `03 §4`, `Q-5` закрыт); `staleness_threshold_hours` = **26** — назначено решением, нигде в репозитории не было и угадыванию не подлежало.
