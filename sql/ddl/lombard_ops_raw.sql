-- T-1-1 · DDL слоя сырья lombard_ops (europe-west3)
-- ГЕНЕРИРУЕТСЯ из connector/mapping.json -> schema_fingerprint (T-0-10),
-- не пишется от руки (ADR-083 п.3-4). Правило типов — закрытый список
-- семи кодов Firebird; код вне списка стопит генератор (UnknownTypeCode).
-- Источник истины: 02_DATA_CONTRACTS.md §2. Не редактировать руками —
-- перегенерировать: python3 connector/generate_raw_ddl.py

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_contracts` (
  contract_id INT64,
  filial_id INT64,
  client_id INT64,
  agent_id INT64,
  contract_num STRING,
  contract_date DATE,
  contract_state INT64,
  contract_close DATE,
  is_archive INT64,
  modify_date TIMESTAMP,
  note STRING,
  id_native INT64,
  id_prev_contract INT64,
  bcode STRING,
  plan_close_date DATE,
  deposit_sum INT64,
  subject_price INT64,
  deposit_type INT64,
  id_deposit_place INT64,
  exchange_rate INT64,
  is_used_in_statistics INT64,
  sum_round_precision INT64,
  allow_sms INT64,
  note_on_close_contract STRING,
  is_not_calc_first_day INT64,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_contracts_terms` (
  id_term INT64,
  contract_id INT64,
  penalty_days INT64,
  deposit_perc NUMERIC,
  penalty_perc NUMERIC,
  is_perc_stop_w_pen INT64,
  exceed_days INT64,
  exceed_months INT64,
  is_privilege_in_exceed_days INT64,
  is_penal_from_ret_sum INT64,
  min_perc_days INT64,
  storage_type INT64,
  storage_val NUMERIC,
  is_storage_stop_w_pen INT64,
  storage_min_days INT64,
  use_exchange INT64,
  use_exchange_if_increase INT64,
  is_pay_perc_on_future INT64,
  acc_pay_scheme STRING,
  insure_type INT64,
  insure_val NUMERIC,
  is_insure_stop_w_pen INT64,
  insure_min_days INT64,
  start_moment INT64,
  id_op INT64,
  tariff_name STRING,
  id_tarif INT64,
  is_auto_on_sale INT64,
  is_close_via_sms INT64,
  is_close_via_photo INT64,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_subjects` (
  id INT64,
  id_contract INT64,
  name STRING,
  price INT64,
  deposit_sum INT64,
  items_count INT64,
  id_native INT64,
  note STRING,
  id_bcode_subj INT64,
  id_files_photo INT64,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_custom_fields_values` (
  id INT64,
  id_field INT64,
  id_obj INT64,
  field_value STRING,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_dir_custom_fields` (
  id INT64,
  id_obj_table INT64,
  name STRING,
  default_value STRING,
  doc_code STRING,
  sort_order INT64,
  id_sub_type INT64,
  field_type INT64,
  cb_items STRING,
  is_requried INT64,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_tables_table` (
  id INT64,
  dbtable STRING,
  table_name STRING,
  name_categ_docs STRING,
  name_log_obj STRING,
  sql_get_log_obj STRING,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_contract_states` (
  state_id INT64,
  code STRING,
  sort_order INT64,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_deposit_types` (
  id INT64,
  code STRING,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `lombard_ops.raw_operations` (
  op_id INT64,
  deposit_id INT64,
  op_vid INT64,
  op_date DATE,
  non_calc_days INT64,
  op_sum INT64,
  op_perc_sum_main INT64,
  op_perc_sum_add INT64,
  op_storage_sum INT64,
  op_penalty_sum INT64,
  op_info STRING,
  id_native INT64,
  op_rest_perc_main INT64,
  op_rest_storage_main INT64,
  op_rest_penalty_main INT64,
  op_rest_base INT64,
  op_rest_perc_add INT64,
  op_rest_storage_add INT64,
  op_rest_penalty_add INT64,
  perc_acc_days INT64,
  stor_acc_days INT64,
  pen_acc_days INT64,
  op_insure_sum INT64,
  op_rest_insure_main INT64,
  op_rest_insure_add INT64,
  insure_acc_days INT64,
  cash INT64,
  change INT64,
  refin_sum_dbl FLOAT64,
  op_rest_perc_main_dbl FLOAT64,
  is_online INT64,
  id_online_filial INT64,
  id_online_native INT64,
  id_agent INT64,
  loaded_at TIMESTAMP NOT NULL,
  source_blob STRING NOT NULL
);
