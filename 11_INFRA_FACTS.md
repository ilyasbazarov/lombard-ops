# 11 · INFRA_FACTS — Канонический реестр ресурсов

**Статус:** LIVE, обновляется только через INFRA_PATCH. Репо публичный — endpoint'ы контура клиента и любые креды сюда НЕ пишутся (ADR-001); их место указано в колонке «Где лежит».

## GCP
| Факт | Значение |
|---|---|
| PROJECT_ID | `project-c451b48a-07ae-4de4-961` |
| PROJECT_NUMBER | `450925595005` |
| Имя проекта | My First Project (косметика, не менять — так сойдёт) |
| Владелец | корпоративный аккаунт клиента; Ilyas — **owner** (замер 2026-08-12, `T-0-7` шаг 1: `gcloud projects get-iam-policy` печатает `roles/owner` + `roles/resourcemanager.projectMover`). Прежняя запись «editor» не подтвердилась; `00_CHARTER.md §4` называет то же самое и STABLE-документ правкой этого исполнителя не тронут — расхождение открыто до ADR архитектора |
| Регион ресурсов | **`europe-west3`** (Франкфурт) — решение владельца 2026-08-12, `ADR-046`; `Q-2` закрыт. Меняется только переездом |
| Датасет BQ | `lombard_ops`, `europe-west3` — создан 2026-08-12 (`T-0-7`). Шесть таблиц (не семь — `02 §2`, поправка счёта коммитом `2c32c3b`): `loans_raw`, `events` (`PARTITION BY DATE(timestamp)`, `CLUSTER BY contract_id`), `offers`, `pricing_snapshots`, `vehicle_catalog`, `assessments`. `bq show` печатает `"location": "europe-west3"` — замер `reference/T-0-7_gcp_foundation_measurement_2026-08-12.md` |
| Бакеты | `${PROJECT_ID}-{photos,config,cfsource}` — созданы 2026-08-12 (`T-0-7`) в `europe-west3`, единый доступ на уровне бакета, `public_access_prevention: enforced` |
| SA конвейера | `lombard-pipeline@${PROJECT_ID}.iam.gserviceaccount.com` — создан 2026-08-12 (`T-0-7`). Роли: `WRITER` на датасете `lombard_ops` (dataset ACL — `bq add-iam-policy-binding` недоступен, `This feature requires allowlisting`, метод в `scripts/gcp_foundation.sh`), `roles/storage.objectAdmin` на всех трёх бакетах, `roles/secretmanager.secretAccessor` на проекте. Project-level `editor`/`owner` не выданы. Ключ SA этой задачей НЕ создан — заводится `T-0-8` |
| Secret Manager | `telegram-bot-token`, `firebird-readonly-creds`, `chat_id` — созданы 2026-08-12 (`T-0-7`) в `europe-west3`, по одной плейсхолдерной версии каждый. Реальные значения не заведены и не запрошены |

## Контур клиента (ERP)
| Факт | Значение | Где лежит секрет |
|---|---|---|
| ERP | PawnShop от «Алгоритм» | — |
| Сервер | Windows Server, LAN: 192.168.88.209 (адрес LAN и RDP совпадают, RDP 3389); адаптер Realtek PCIe GbE (один); VPN-туннель терминируется на роутере, не на сервере; работает 24/7, ИБП нет (техдолг ADR-008) | админ-креды — у Ilyas (от Исы) |
| СУБД | Firebird **2.5.9**, порт **3057**, слушает 0.0.0.0, служба `FirebirdServerPawnShop-3057` | — |
| Путь Firebird | `C:\Program Files (x86)\Firebird-2.5-PawnShop\` | — |
| Путь к .fdb | `D:\PawnShop_DOL\DB\DOL.FDB` (измерено `T-0-5`, 2026-08-11) | — |
| Креды SYSDBA | ⏳ | вне репо |
| Пользователь `LOMBARD_RO` | существует, пароль известен владельцу (подтверждено подключением); свои гранты — `SELECT` на 9 таблиц из `briefs/T-0-5.md`. **НЕ read-only фактически.** Измерено `T-0-5`, 2026-08-11: `PUBLIC` несёт `SELECT` на 107 таблицах базы (всего таблиц 108 по замеру `T-0-2`) и права записи `D`/`I`/`U` каждое на 104 объектах (шаг 6-ж, `reference/T-0-5_readonly_mode_measurement_2026-08-11.md`). Гранты `PUBLIC` не отзываются (`ADR-032`, письмо вендору снято `ADR-034`, риск постоянный). **Режим `SET TRANSACTION READ ONLY` на клиентской стороне подтверждён замером: движок его переключает** (шаг 6-е-БИС, `MON$READ_ONLY` разное между прогонами при разных номерах транзакций, тот же артефакт) — **уровень отказа ИЗМЕРЕН 2026-08-12 на нашем экземпляре Firebird 2.5.9** (`T-0-17`, `ADR-037`, `Q-17` закрыт): отказ приходит на уровне ЗАДЕВАЕМОЙ ЗАПИСИ — `SQLSTATE = 42000`, `attempted update during read-only transaction`; оператор с нулём задетых строк проходит молча и режим не измеряет. На базе клиента решающая проба запрещена `00 §4`, поэтому факт перенесён с нашего экземпляра той же версии, а не снят на прод-базе. Учётка по-прежнему не используется как ЕДИНСТВЕННАЯ защита от записи: основной контроль — белый список операторов в нашем слое — ещё не заведён. Замеры: `reference/T-0-5_readonly_measurement_2026-08-11.md`, `reference/T-0-5_readonly_tx_measurement_2026-08-11.md` (снятый шаг 6-е), `reference/T-0-5_readonly_mode_measurement_2026-08-11.md` (шаги 6-е-БИС и 6-ж), `reference/T-0-17_readonly_engine_measurement_2026-08-12.md` (уровень отказа, наш экземпляр) | вне репо (пароль) |
| Кодировка данных | UTF-8 | — |
| Firewall | частный профиль ON; правило «Firebird 3057 (VPN+LAN only)» — inbound TCP 3057 для 192.168.88.0/24 и подсети VPN | — |
| Доступ извне | VPN WireGuard через роутер клиента (Keenetic Voyager Pro KN-3510, прошивка 5.0.x); белый, возможно динамический IP + DDNS | endpoint, порт WG и .conf-файлы — у Ilyas, вне репо |
| VPN-пользователи | peer для Ilyas + peer `lombard-connector` под автоматику | ключи — у Ilyas, вне репо |

| Канал прод-подключения | **агент на сервере клиента** (вариант Б `01 §4`) — решение владельца 2026-08-12, `ADR-046`; `Q-3` закрыт. Только исходящий трафик, входящие соединения к контуру клиента не нужны. Реализация — `T-0-8`; связность агент→GCS проверяется ПЕРВЫМ шагом, до кода |

## Внешние сервисы
| Факт | Значение |
|---|---|
| Telegram Bot | ⏳ создать (@BotFather), token → Secret Manager |
| chat_id Иса/Бектур/Эльхан | ⏳ собрать, → Secret Manager/config |
| Репо | `github.com/ilyasbazarov/lombard-ops`, public |
