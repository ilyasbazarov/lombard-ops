-- T-0-17, шаг 5: создание выброшенной базы и одной строки на собственном экземпляре Firebird 2.5.9.
-- Прогоняется внутри контейнера jacobalberty/firebird:2.5.9-sc через isql -i.
CREATE DATABASE '/tmp/probe.fdb';
CREATE TABLE PROBE (ID INTEGER NOT NULL, TXT VARCHAR(16));
INSERT INTO PROBE (ID, TXT) VALUES (1, 'row');
COMMIT;
SELECT COUNT(*) AS CNT_SETUP FROM PROBE;
