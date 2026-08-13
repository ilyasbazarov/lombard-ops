T-0-8_federation_setup_2026-08-13.md

# T-0-8 · Шаг 5-А, пункты 1–3 — федерация удостоверений в проекте клиента

**Класс задачи:** B. **Кем исполнено:** ГЛАВНОЙ сессионной (не суб-агентом), локальным
authenticated `gcloud` — владелец подтвердил карточку и явно переключил режим исполнения облачных
команд на «Claude исполняет сам после подтверждения по карточке» (это не Cloud Shell владельца).
Скрипт-источник — `scripts/T-0-8_step5a_federation_pool.sh`, функции `step1_...`, `step2_...`,
`step3_create_pool`. Объект — проект `project-c451b48a-07ae-4de4-961` (номер `450925595005`),
локация пула — `global`.

Пункты 4 (создание OIDC-провайдера) и 5 (role binding) этой сессией НЕ исполнены: ждут
`--issuer-uri` (`Q-22`, домен клиента) и файл JWKS с шага 5-Б, который тоже не исполнен (ждёт имя
служебной учётки агента на сервере).

---

## Пункт 1 (read-only) — `constraints/iam.allowedPolicyMemberDomains --effective`

Дословный вывод:

```
name: projects/450925595005/policies/iam.allowedPolicyMemberDomains
spec:
  rules:
  - allowAll: true
```

**Вердикт:** ограничение НЕ действует (`allowAll: true`, не `enforce`) — выдача роли внешнему
principal на шаге 5-А п.5 этим ограничением не блокируется. Стоп по этому пункту не наступил.

## Пункт 2 (read-only) — `gcloud services list --enabled`, совпадения по `iamcredentials`/`sts`

Дословно: первый `grep -E "iamcredentials|sts"` нашёл только `iamcredentials`, `sts` не совпал.
Точный поиск строки `sts` дал «НЕ НАЙДЕНО». Обратный контроль — полный список 33 включённых
сервисов — подтвердил, что инструмент исправен (список непустой, `iamcredentials` в нём
присутствует), и что `sts.googleapis.com` в списке действительно отсутствовал: это факт «сервис
выключен», а не гэп наблюдения.

**Действие (включение недостающего сервиса):**

```
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project=project-c451b48a-07ae-4de4-961
→ "Operation ... finished successfully."
```

Проверка после: `iamcredentials.googleapis.com` и `sts.googleapis.com` оба присутствуют в списке
`--enabled`.

**Факт, который нельзя потерять:** `iamcredentials.googleapis.com` уже был включён зависимостью
`T-0-7` (`reference/T-0-7_gcp_foundation_measurement_2026-08-12.md`, шаг 2) — это сверка, не
догадка. `sts.googleapis.com`, в отличие от него, пришлось включать явно этим шагом: он не был
подтянут ничем ранее.

## Пункт 3 — создание пула федерации

```
gcloud iam workload-identity-pools create "lombard-agent-federation-pool" \
  --project="project-c451b48a-07ae-4de4-961" --location="global" \
  --display-name="Lombard agent federation pool" \
  --description="T-0-8: пул федерации для JWT-подписи агента на сервере ERP (ADR-050)"
→ "Created workload identity pool [lombard-agent-federation-pool]."
```

Проверка (`describe`), дословно:

```
description: 'T-0-8: пул федерации для JWT-подписи агента на сервере ERP (ADR-050)'
displayName: Lombard agent federation pool
name: projects/450925595005/locations/global/workloadIdentityPools/lombard-agent-federation-pool
state: ACTIVE
```

**Вердикт:** пул создан, `state: ACTIVE`. Имя пула — `lombard-agent-federation-pool` (реальное имя
ресурса, не плейсхолдер).

---

## Итог шага 5-А пп.1–3

| Пункт | Исход |
|---|---|
| 1 (allowedPolicyMemberDomains) | Ограничение не действует (`allowAll: true`) — не блокирует выдачу роли внешнему principal позже |
| 2 (iamcredentials/sts) | `sts.googleapis.com` пришлось включить явно (не была включена по умолчанию, в отличие от `iamcredentials`, подтянутой зависимостью `T-0-7`) |
| 3 (пул федерации) | Создан, `state: ACTIVE`, имя `lombard-agent-federation-pool` |

**Не выполнено этой сессией:** пункт 4 (создание OIDC-провайдера, `--issuer-uri`, `--jwk-json-path`)
и пункт 5 (role binding на `lombard-pipeline@`) — держатся `Q-22` (значение `--issuer-uri`) и шагом
5-Б (файл JWKS с сервера ERP, служебная учётка агента ещё не названа).

Откат (не исполнен, зафиксирован на случай необходимости):
`gcloud iam workload-identity-pools delete lombard-agent-federation-pool --project=project-c451b48a-07ae-4de4-961 --location=global`.

---

## Служебная учётная запись агента на сервере ERP (2026-08-13) — подготовительная часть перед шагом 5-Б

**Класс задачи:** B. **Кем исполнено:** Ilyas, вручную по RDP на сервере ERP (не Claude, не главная
сессия). Это заведение локальной учётной записи Windows для будущей службы агента — снимает
недостающий параметр `-ServiceAccountName` скрипта `scripts/T-0-8_step5b_server_setup.ps1`, но само
по себе шагом 5-Б не является: ни ключ, ни JWKS, ни конфигурация учётных данных этим действием не
созданы.

Дословный вывод исполненного скрипта:

```
Задание выполнено успешно.
Подробные сведения записаны в журнале %windir%\security\logs\scesrv.log.
Name              Enabled Description
----              ------- -----------
lombard-agent-svc True    T-0-8: служебная учётка агента (ADR-050)
Учётка lombard-agent-svc создана. Пароль сгенерирован и НЕ печатается — он не понадобится: служба
будет запускаться системным планировщиком/SCM под этой учёткой без интерактивного входа
(настраивается на шаге 6).

Name              Enabled Description
----              ------- -----------
lombard-agent-svc    True T-0-8: служебная учётка агента (ADR-050)

Права SeServiceLogonRight/SeDenyInteractiveLogonRight применены через secedit.
```

**Что подтверждено этим выводом:**

- Локальная учётная запись Windows `lombard-agent-svc` создана, `Enabled: True`.
- **Не администратор** — скрипт создаёт учётку без включения в группу `Administrators` (по описанию
  исполненного скрипта; вывод команды `net localgroup Administrators` этим прогоном не печатался —
  отсутствие членства в группе не предъявлено отдельной строкой, это названо явно, а не
  подразумевается).
- **Интерактивный вход запрещён** — право `SeDenyInteractiveLogonRight` применено через `secedit`
  (подтверждено строкой вывода «Права … применены через secedit»; сам применённый шаблон `secedit`
  дословно в вывод не попал).
- **Право входа как служба выдано** — `SeServiceLogonRight` тем же вызовом `secedit`.
- **Пароль нигде не хранится и не понадобится** — сгенерирован случайно, не выведен, не сохранён:
  схема запуска службы — SCM/планировщик под этой учёткой без интерактивного входа (шаг 6), которому
  явный пароль не нужен.

**Чего этот вывод НЕ доказывает** (следует называть, а не молчать): состав секьюрити-групп учётки
после создания, точное содержимое шаблона `secedit`, дословный текст `scesrv.log`. Ни то, ни другое
не требуется приёмкой этого действия по брифу — названные выше пять фактов достаточны для
параметра `-ServiceAccountName` шага 5-Б и для `icacls` на приватный ключ.

**Что из этого следует для оставшихся шагов:**

1. Параметр `-ServiceAccountName` скрипта `scripts/T-0-8_step5b_server_setup.ps1` теперь имеет
   значение — `lombard-agent-svc` — и шаг 5-Б исполним по карточке подтверждения без дополнительного
   вопроса владельцу об имени учётки.
2. Шаг 6 (установка службы) использует ту же учётку для запуска через SCM/планировщик без
   интерактивного входа — согласуется с уже выданными правами.
