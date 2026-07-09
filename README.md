# lombard-ops

Операционная система автоломбарда «Омега Экспресс»: фильтр на входе → светофор по циклу → stop-loss реализации.
Данные читаются напрямую из БД ERP PawnShop (Firebird, read-only) и проецируются в GCP (BigQuery + Cloud Run + Cloud Functions). Интерфейс владельца — Telegram; веб-приложение — с авторизацией и ролями.

## Карта базы знаний

| Файл | Назначение | Статус |
|---|---|---|
| `00_CHARTER.md` | Конституция проекта: scope, границы, красные линии | STABLE |
| `01_ARCHITECTURE.md` | Компоненты и потоки данных | SEMI-STABLE |
| `02_DATA_CONTRACTS.md` | Схемы BigQuery, маппинг PawnShop → canonical | SEMI-STABLE |
| `03_BUSINESS_SPEC.md` | Статусная модель, три цены, floor, справочник ликвидности | SEMI-STABLE |
| `04_ROADMAP.md` | Фазы, задачи, зависимости, критерии приёмки | LIVE |
| `05_CONVENTIONS.md` | Правила агентов + технические стандарты. **Читается первым в любой сессии** | SEMI-STABLE |
| `06_DECISIONS_LOG.md` | ADR, append-only | LIVE |
| `07_STATE.md` | Текущее состояние и фокус | LIVE |
| `08_TASK_BRIEF_TEMPLATE.md` | Шаблон task-брифа | STABLE |
| `09_GLOSSARY.md` | Термины и участники | STABLE |
| `10_GCP_INFRA_PLAYBOOK.md` | Грабли и рецепты GCP | LIVE |
| `11_INFRA_FACTS.md` | Канонический реестр ресурсов | LIVE |

## Запуск ролей (свежий чат)

- **Архитектор (Opus)** — вставить raw-URL `_ARCHITECT.md`, назвать вопрос/задачу.
- **Разработчик (Sonnet)** — вставить конкретный task-brief из `/briefs`.
- **Генератор брифов (Sonnet)** — вставить raw-URL `briefs/_GENERATOR.md`.
- **Applier (Haiku)** — вставить raw-URL `_APPLIER.md` + session-блок для применения.

Raw-URL формат: `https://raw.githubusercontent.com/ilyasbazarov/lombard-ops/main/<FILE>.md`
Внутри сессии перечитывать доки — только по commit-SHA (см. `05_CONVENTIONS`).

## Структура кода

```
/briefs      брифы задач + _GENERATOR.md
/sql         DDL и трансформации BigQuery
/connector   коннектор Firebird → BigQuery
/functions   cf-daily, cf-tg-handler
/app         веб-приложение (Cloud Run: React + API)
/scripts     setup-блоки gcloud, сиды, одноразовые скрипты
```

## Санитария публичного репо (ADR-001)

В репо НИКОГДА не попадают: креды и ключи (в т.ч. VPN-конфиги), публичные endpoint'ы контура клиента (DDNS-имена, порты VPN), персональные данные клиентов ломбарда, токены Telegram. Место секретов — GCP Secret Manager.
