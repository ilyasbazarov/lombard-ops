-- T-0-7 · DDL датасета lombard_ops (europe-west3)
-- Источник истины: 02_DATA_CONTRACTS.md §2. Шесть таблиц (поправка счёта 2026-08-12, коммит 2c32c3b).
-- Явные схемы: SELECT * / autodetect не используются нигде по конвейеру (05 §II).

CREATE TABLE IF NOT EXISTS `lombard_ops.loans_raw` (
  contract_id STRING NOT NULL,
  vehicle_id STRING,
  client_name STRING,
  vehicle_make STRING,
  vehicle_model STRING,
  vehicle_year INT64,
  loan_amount NUMERIC,
  issue_date DATE,
  due_date DATE,
  status_raw STRING,
  renewed BOOL,
  renewed_date DATE,
  loaded_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.events` (
  event_id STRING NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  contract_id STRING NOT NULL,
  vehicle_id STRING,
  event_type STRING NOT NULL,
  payload JSON,
  actor STRING,
  idempotency_key STRING NOT NULL
)
PARTITION BY DATE(timestamp)
CLUSTER BY contract_id;

CREATE TABLE IF NOT EXISTS `lombard_ops.offers` (
  offer_id STRING NOT NULL,
  contract_id STRING NOT NULL,
  vehicle_id STRING,
  offer_date DATE,
  buyer_contact STRING,
  offer_amount NUMERIC,
  vs_floor NUMERIC,
  decision STRING,
  decided_by STRING,
  decided_at TIMESTAMP,
  tg_message_id STRING
);

CREATE TABLE IF NOT EXISTS `lombard_ops.pricing_snapshots` (
  contract_id STRING NOT NULL,
  calc_date DATE NOT NULL,
  balance_amount NUMERIC,
  realization_price NUMERIC,
  floor_price NUMERIC,
  floor_pct NUMERIC,
  depreciation_coeff NUMERIC,
  days_since_default INT64
);

-- price_source/comment добавлены T-2-4 (02 §2): справочник ликвидности несёт метку синтетики.
CREATE TABLE IF NOT EXISTS `lombard_ops.vehicle_catalog` (
  make STRING NOT NULL,
  model STRING NOT NULL,
  liquidity_class STRING,
  ltv_max NUMERIC,
  buyout_price NUMERIC,
  price_source STRING,
  comment STRING,
  updated_at TIMESTAMP
);

-- CONTEXT GAP (не снят, 2026-08-12): 02 §2 задаёт поле `*_discount` как wildcard —
-- несколько колонок по факторам дисконта (03 §5: кузов, толщиномер, пробег, владельцы по ПТС),
-- конкретные английские имена колонок нигде не названы. Колонки по факторам НЕ добавлены —
-- угадывать имена запрещено (anti-improvisation). `total_discount` включена: она названа явно.
-- Снимается вопросом архитектору/владельцу; до снятия — открытый вопрос (см. session-блок).
CREATE TABLE IF NOT EXISTS `lombard_ops.assessments` (
  assessment_id STRING NOT NULL,
  contract_id STRING NOT NULL,
  vehicle_id STRING,
  make STRING,
  model STRING,
  vin STRING,
  year INT64,
  mileage INT64,
  total_discount NUMERIC,
  base_price NUMERIC,
  max_loan NUMERIC,
  photos_gcs_path STRING,
  assessor STRING,
  created_at TIMESTAMP NOT NULL,
  -- Применённые факторы оценки: вложенная запись, не колонки (ADR-058, ADR-093 вариант 1).
  -- Новый фактор заводится строкой справочника, схема таблицы при этом не меняется.
  -- factor_id  — идентификатор из справочника факторов (data_inbox/factor_catalog.csv);
  -- value      — что ввёл оценщик (флаг/деление шкалы/число диапазона), строкой как показано;
  -- weight     — вес фактора на момент осмотра, копируется из справочника (историю не переписываем);
  -- discount   — вклад фактора в total_discount, доля: -0.05 = минус 5 %.
  applied_factors ARRAY<STRUCT<
    factor_id STRING,
    value STRING,
    weight NUMERIC,
    discount NUMERIC
  >>
);
