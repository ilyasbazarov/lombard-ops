-- sql/canonization.sql · T-1-2a · Канонизация (SQL) + детектор продлений + статус 03 §1
--
-- Источник истины на бизнес-правила: 03_BUSINESS_SPEC.md §1 (статусная модель) и §2 (Renewals);
-- на схему сырья: 02_DATA_CONTRACTS.md §2, sql/ddl/lombard_ops_raw.sql (сгенерирован из
-- connector/mapping.json, T-0-10); на целевую схему: sql/ddl/lombard_ops.sql (`loans_raw`).
--
-- ПРИМЕНЕНИЕ В BIGQUERY — предмет T-1-2b (класс B, применение view и прогон в датасете), не этой
-- задачи. Эта задача только пишет и офлайн-тестирует текст (connector/canonize/), к BigQuery не
-- обращается вовсе (00 §4, ограничения брифа T-1-2a).
--
-- `client_name` и `vehicle_*` этой задачей НЕ наполняются (Q-30, T-1-2b) — явные NULL-колонки
-- ниже, а не отсутствие полей: молчания о них в выводе canonical view быть не должно.
--
-- Единственная реализация статуса `03 §1` (ADR-089 п.2, портировано из
-- functions/cf_daily/status.py дословно по порогам и staircase-решению T-1-0; за Python остаётся
-- АДРЕСАТ алерта, не статус — эта задача его не считает).

-- ---------------------------------------------------------------------------------------------
-- Шаг 5 · Выбор снапшота (дедупликация по loaded_at/source_blob)
-- Применяется к таблицам, где повторная загрузка может дать несколько строк на один ключ
-- источника: `raw_contracts` (первичная сущность канонизации) и `raw_contract_states`
-- (справочник, используемый JOIN'ом ниже). `raw_operations` дедупликации в этой задаче не
-- требует: ветвь «Погашение» (шаг 3) агрегирует по `deposit_id` через `MAX(op_date)` и считает
-- DISTINCT договоров — повтор той же операции в двух снапшотах не меняет ни максимум даты, ни
-- множество договоров.
-- ---------------------------------------------------------------------------------------------

CREATE OR REPLACE VIEW `lombard_ops.v_raw_contracts_dedup` AS
SELECT * EXCEPT(rn)
FROM (
  SELECT
    c.*,
    ROW_NUMBER() OVER (PARTITION BY c.contract_id ORDER BY c.loaded_at DESC) AS rn
  FROM `lombard_ops.raw_contracts` c
)
WHERE rn = 1;

CREATE OR REPLACE VIEW `lombard_ops.v_raw_contract_states_dedup` AS
SELECT * EXCEPT(rn)
FROM (
  SELECT
    s.*,
    ROW_NUMBER() OVER (PARTITION BY s.state_id ORDER BY s.loaded_at DESC) AS rn
  FROM `lombard_ops.raw_contract_states` s
)
WHERE rn = 1;

-- ---------------------------------------------------------------------------------------------
-- Шаг 1 · status_raw: raw_contracts.contract_state -> raw_contract_states.state_id -> code
-- (02 §3 «действующий расклад»: status_raw — работа T-1-2, источник CONTRACTS.CONTRACT_STATE ->
-- CONTRACT_STATES, внутри белого списка девяти таблиц).
-- ---------------------------------------------------------------------------------------------

CREATE OR REPLACE VIEW `lombard_ops.v_status_raw` AS
SELECT
  c.contract_id,
  cs.code AS status_raw
FROM `lombard_ops.v_raw_contracts_dedup` c
LEFT JOIN `lombard_ops.v_raw_contract_states_dedup` cs
  ON c.contract_state = cs.state_id;

-- ---------------------------------------------------------------------------------------------
-- Шаг 2 · Детектор продлений — ветвь «Переоткрытие» (03 §2)
-- CONTRACTS.ID_PREV_CONTRACT не пусто -> новая строка ссылается на предыдущую; начало нового
-- цикла — issue_date (CONTRACT_DATE) этой же новой строки.
-- ---------------------------------------------------------------------------------------------

CREATE OR REPLACE VIEW `lombard_ops.v_renewal_reopen` AS
SELECT
  contract_id,
  TRUE AS renewed_reopen,
  contract_date AS renewed_date_reopen
FROM `lombard_ops.v_raw_contracts_dedup`
WHERE id_prev_contract IS NOT NULL;

-- ---------------------------------------------------------------------------------------------
-- Шаг 3 · Детектор продлений — ветвь «Погашение» (03 §2)
-- OPERATIONS.OP_VID = 0 (ovPay, «погашение с продлением договора»), присоединяется по
-- OPERATIONS.DEPOSIT_ID = CONTRACTS.CONTRACT_ID. Дата продления — последняя такая операция на
-- договор (MAX(op_date)).
-- ---------------------------------------------------------------------------------------------

CREATE OR REPLACE VIEW `lombard_ops.v_renewal_repayment` AS
SELECT
  deposit_id AS contract_id,
  TRUE AS renewed_repayment,
  MAX(op_date) AS renewed_date_repayment
FROM `lombard_ops.raw_operations`
WHERE op_vid = 0
GROUP BY deposit_id;

-- ---------------------------------------------------------------------------------------------
-- Шаг 4 · Объединение обеих ветвей через OR (03 §2)
-- renewed_date: если сработали обе ветви, берётся более поздняя дата (продление есть событие,
-- дата которого не может быть раньше самого позднего из двух независимо найденных признаков);
-- если сработала одна — её дата; если ни одна — NULL. Явный CASE вместо GREATEST — GREATEST в
-- BigQuery возвращает NULL при любом NULL-аргументе, что здесь неверно на "сработала только одна
-- ветвь".
-- ---------------------------------------------------------------------------------------------

CREATE OR REPLACE VIEW `lombard_ops.v_renewal` AS
SELECT
  c.contract_id,
  (COALESCE(a.renewed_reopen, FALSE) OR COALESCE(b.renewed_repayment, FALSE)) AS renewed,
  CASE
    WHEN a.renewed_date_reopen IS NOT NULL AND b.renewed_date_repayment IS NOT NULL
      THEN GREATEST(a.renewed_date_reopen, b.renewed_date_repayment)
    WHEN a.renewed_date_reopen IS NOT NULL THEN a.renewed_date_reopen
    WHEN b.renewed_date_repayment IS NOT NULL THEN b.renewed_date_repayment
    ELSE CAST(NULL AS DATE)
  END AS renewed_date
FROM `lombard_ops.v_raw_contracts_dedup` c
LEFT JOIN `lombard_ops.v_renewal_reopen` a USING (contract_id)
LEFT JOIN `lombard_ops.v_renewal_repayment` b USING (contract_id);

-- ---------------------------------------------------------------------------------------------
-- Шаг 7 · Формула статуса 03 §1 — единственная реализация (ADR-089 п.2)
-- Портировано дословно из functions/cf_daily/status.py::compute_status (пороги + решение
-- исполнителя T-1-0 про staircase). Точечные дни +39/+46/+62 статус НЕ меняют (сужают только
-- адресата в Python) — эта задача адресата не считает, поэтому здесь их нет вовсе.
--
-- Функция принимает УЖЕ вычисленное смещение (offset_days = today - due_date, дни) — вынесено
-- отдельно от вычисления смещения (`lombard_ops.offset_days` ниже), чтобы staircase можно было
-- тестировать на синтетических смещениях напрямую (шаг 8, таблица эквивалентности), а не только
-- через CURRENT_DATE().
-- ---------------------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION `lombard_ops.status_for_offset`(offset_days INT64) AS (
  CASE
    WHEN offset_days <= -7 THEN '🟢 Активный'
    WHEN offset_days BETWEEN -6 AND 1 THEN '🟡 Внимание'
    WHEN offset_days BETWEEN 2 AND 15 THEN '🟠 Просрочен'
    WHEN offset_days BETWEEN 16 AND 31 THEN '🟠 Пре-маркетинг'
    ELSE '🔴 Реализация'
  END
);

-- Смещение от плановой даты (03 §1, ADR-070): offset_days = today − due_date, дни.
CREATE OR REPLACE FUNCTION `lombard_ops.offset_days`(today DATE, due_date DATE) AS (
  DATE_DIFF(today, due_date, DAY)
);

-- ---------------------------------------------------------------------------------------------
-- Шаг 6 · Canonical view
-- По каждому АКТИВНОМУ договору (contract_state = 0, код OPEN — справочник contract_state_catalog,
-- T-0-4a, reference/T-0-4a_renewal_detector_measurement_2026-08-18.md, шаг 12) — issue_date,
-- due_date (PLAN_CLOSE_DATE), смещение, status_raw, renewed/renewed_date, вычисленный статус.
-- `client_name` и `vehicle_*` — явные NULL, не отсутствующие колонки (T-1-2b, Q-30).
-- ---------------------------------------------------------------------------------------------

CREATE OR REPLACE VIEW `lombard_ops.v_canonization` AS
SELECT
  c.contract_id,
  c.contract_date AS issue_date,
  c.plan_close_date AS due_date,
  `lombard_ops.offset_days`(CURRENT_DATE(), c.plan_close_date) AS offset_days,
  sr.status_raw,
  COALESCE(r.renewed, FALSE) AS renewed,
  r.renewed_date,
  `lombard_ops.status_for_offset`(
    `lombard_ops.offset_days`(CURRENT_DATE(), c.plan_close_date)
  ) AS status,
  CAST(NULL AS STRING) AS client_name,   -- Q-30 — не наполняется этой задачей
  CAST(NULL AS STRING) AS vehicle_id,    -- T-1-2b
  CAST(NULL AS STRING) AS vehicle_make,  -- T-1-2b (ADR-086, разбор строки модели)
  CAST(NULL AS STRING) AS vehicle_model, -- T-1-2b
  CAST(NULL AS INT64) AS vehicle_year    -- T-1-2b/ADR-087 — источника нет, поле остаётся пустым
FROM `lombard_ops.v_raw_contracts_dedup` c
LEFT JOIN `lombard_ops.v_status_raw` sr USING (contract_id)
LEFT JOIN `lombard_ops.v_renewal` r USING (contract_id)
WHERE c.contract_state = 0;
