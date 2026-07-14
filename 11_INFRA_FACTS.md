# 11 · INFRA_FACTS — Канонический реестр ресурсов

**Статус:** LIVE, обновляется только через INFRA_PATCH. Репо публичный — endpoint'ы контура клиента и любые креды сюда НЕ пишутся (ADR-001); их место указано в колонке «Где лежит».

## GCP
| Факт | Значение |
|---|---|
| PROJECT_ID | `project-c451b48a-07ae-4de4-961` |
| PROJECT_NUMBER | `450925595005` |
| Имя проекта | My First Project (косметика, не менять — так сойдёт) |
| Владелец | корпоративный аккаунт клиента; Ilyas — editor |
| Регион ресурсов | ⏳ решить в T-0-7 |
| Датасет BQ | `lombard_ops` ⏳ создать (T-0-7) |
| Бакеты | `${PROJECT_ID}-{photos,config,cfsource}` ⏳ (T-0-7) |
| SA конвейера | `lombard-pipeline@` ⏳ (T-0-7) |
| Secret Manager | ⏳ секреты: telegram-bot-token, firebird-readonly-creds, chat_id (T-0-7) |

## Контур клиента (ERP)
| Факт | Значение | Где лежит секрет |
|---|---|---|
| ERP | PawnShop от «Алгоритм» | — |
| Сервер | Windows Server, LAN: 192.168.88.209 (адрес LAN и RDP совпадают, RDP 3389); адаптер Realtek PCIe GbE (один); VPN-туннель терминируется на роутере, не на сервере; работает 24/7, ИБП нет (техдолг ADR-008) | админ-креды — у Ilyas (от Исы) |
| СУБД | Firebird **2.5.9**, порт **3057**, слушает 0.0.0.0, служба `FirebirdServerPawnShop-3057` | — |
| Путь Firebird | `C:\Program Files (x86)\Firebird-2.5-PawnShop\` | — |
| Путь к .fdb, креды SYSDBA | ⏳ найти на сервере (T-0-2) | вне репо |
| Кодировка данных | UTF-8 | — |
| Firewall | частный профиль ON; правило «Firebird 3057 (VPN+LAN only)» — inbound TCP 3057 для 192.168.88.0/24 и подсети VPN | — |
| Доступ извне | VPN WireGuard через роутер клиента (Keenetic Voyager Pro KN-3510, прошивка 5.0.x); белый, возможно динамический IP + DDNS | endpoint, порт WG и .conf-файлы — у Ilyas, вне репо |
| VPN-пользователи | peer для Ilyas + peer `lombard-connector` под автоматику | ключи — у Ilyas, вне репо |

## Внешние сервисы
| Факт | Значение |
|---|---|
| Telegram Bot | ⏳ создать (@BotFather), token → Secret Manager |
| chat_id Иса/Бектур/Эльхан | ⏳ собрать, → Secret Manager/config |
| Репо | `github.com/ilyasbazarov/lombard-ops`, public |
