# T-2-4 — заливка сида в vehicle_catalog, 2026-08-20

Карточка 1 (шаг 10 брифа `T-2-4`) подтверждена владельцем 2026-08-20, исполнена
`scripts/T-2-4_load_catalog.sh`.

## Диагностика ДО

```
row_count
0
```

## ALTER TABLE

`ALTER TABLE lombard_ops.vehicle_catalog ADD COLUMN price_source STRING, ADD COLUMN comment STRING`
— применено, job DONE.

## bq load — найденная и исправленная ошибка

Первая попытка (текстовая схема `make:STRING,model:STRING,...`) провалилась:
`Field make has changed mode from REQUIRED to NULLABLE` — реальная таблица несёт
`make STRING REQUIRED`, `model STRING REQUIRED` (подтверждено `bq show --format=prettyjson`).

Вторая попытка (текстовая схема с explicit `:REQUIRED`) провалилась:
`Invalid schema entry: make:STRING:REQUIRED` — инлайн-текстовая схема `bq load` не поддерживает
`MODE`, только `name:type` (документировано `bq load --help`).

Исправление: схема убрана из вызова целиком — таблица уже существует, `bq load` использует её
схему (документированное поведение). Скрипт `scripts/T-2-4_load_catalog.sh` обновлён тем же
изменением, что и лог.

Загрузка: `data_inbox/vehicle_catalog_seed.json`, 6 строк — успех, job DONE.

## Диагностика ПОСЛЕ

Счёт строк: 6.

Распределение по `liquidity_class`: green 3, yellow 2, red 1.

Счёт по `price_source`: synthetic 6 (`data_inbox/vehicle_catalog.csv` не был предоставлен
владельцем на момент исполнения — весь сид синтетический, названо явно).
