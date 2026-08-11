-- T-0-5: выдача SELECT-прав read-only пользователю LOMBARD_RO.
-- Пере-запускаемый: GRANT в Firebird идемпотентен, повторный прогон не даёт ошибок.
-- Без паролей и путей — путь к базе и креды передаются isql отдельно, при подключении.
-- Список таблиц — из briefs/T-0-5.md, раздел "Список таблиц"; connector/mapping.json
-- отсутствует в репозитории (T-0-10 не исполнена), список подставлен из брифа явно.

GRANT SELECT ON CONTRACTS TO LOMBARD_RO;
GRANT SELECT ON CONTRACTS_TERMS TO LOMBARD_RO;
GRANT SELECT ON SUBJECTS TO LOMBARD_RO;
GRANT SELECT ON CUSTOM_FIELDS_VALUES TO LOMBARD_RO;
GRANT SELECT ON DIR_CUSTOM_FIELDS TO LOMBARD_RO;
GRANT SELECT ON TABLES_TABLE TO LOMBARD_RO;
GRANT SELECT ON CONTRACT_STATES TO LOMBARD_RO;
GRANT SELECT ON DEPOSIT_TYPES TO LOMBARD_RO;
GRANT SELECT ON OPERATIONS TO LOMBARD_RO;
