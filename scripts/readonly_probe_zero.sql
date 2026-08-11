-- T-0-17, шаг 7 (измеряемое): проба в транзакции только на чтение, предикат БЕЗ строк.
-- Точная копия шага 6-е задачи T-0-5 плюс контроль RO_FLAG. Подключение к /tmp/probe.fdb
-- задаётся строкой CONNECT перед запуском (см. readonly_probe_row.sql — тот же паттерн).
COMMIT;
SET TRANSACTION READ ONLY;
SELECT MON$READ_ONLY AS RO_FLAG FROM MON$TRANSACTIONS WHERE MON$TRANSACTION_ID = CURRENT_TRANSACTION;
UPDATE PROBE SET ID = ID WHERE 1 = 0;
COMMIT;
