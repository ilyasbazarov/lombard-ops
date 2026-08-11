-- T-0-17, шаг 8 (измеряемое): проба в транзакции только на чтение, предикат НА ОДНУ строку.
COMMIT;
SET TRANSACTION READ ONLY;
UPDATE PROBE SET ID = ID WHERE ID = 1;
COMMIT;
SELECT COUNT(*) AS CNT_AFTER_RO FROM PROBE;
