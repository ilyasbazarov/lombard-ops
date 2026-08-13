# T-0-8 · Замер требований платформы к значению `--issuer-uri` OIDC-провайдера федерации · 2026-08-13

Предмет: закрыть `Q-22` — требует ли платформа, чтобы значение обязательного флага `--issuer-uri`
(`gcloud iam workload-identity-pools providers create-oidc`) указывало на РЕАЛЬНЫЙ, разрешаемый в
сети и принадлежащий кому-либо домен, при условии что открытые ключи загружены напрямую
(`--jwk-json-path`).

Класс A. Печать справки и внутренних файлов локально установленного `Google Cloud SDK 577.0.0`
плюс чтение официальной документации платформы. Ни одного облачного объекта не создано, не
изменено и не прочитано; ни одной команды на проект клиента не отправлено; аутентификация не
требовалась.

Основание для замера — `reference/T-0-8_jwks_delivery_measurement_2026-08-13.md`, раздел «Что этим
замером НЕ установлено», пункт 1: «Примет ли API значение `--issuer-uri`, которое не разрешается в
сети… Различающая проверка — единственная: фактическое создание провайдера».

---

## Замер 1 — справка `create-oidc`: что сказано о формате значения (дословно)

Команда: `gcloud iam workload-identity-pools providers create-oidc --help`.

Секция `REQUIRED FLAGS`, строки 155–156 вывода, дословно и целиком:

```
     --issuer-uri=ISSUER_URI
        The OIDC issuer URL.
```

Больше о значении в справке не сказано ничего: ни требования схемы, ни требования достижимости,
ни требования владения. Пример в `EXAMPLES` той же справки применяет `--issuer-uri="https://test-idp.com"`
ВМЕСТЕ с `--jwk-json-path="path/to/jwk.json"`.

## Замер 2 — есть ли у `gcloud` КЛИЕНТСКАЯ валидация значения (положительный контраст)

Источник: описание флага в самом SDK,
`lib/googlecloudsdk/command_lib/iam/flags.yaml`, строки 386–394 (дословно):

```
  oidc_issuer_uri:
    api_field: workloadIdentityPoolProvider.oidc.issuerUri
    ALPHA:
      api_field: googleIamV1betaWorkloadIdentityPoolProvider.oidc.issuerUri
    BETA:
      api_field: googleIamV1betaWorkloadIdentityPoolProvider.oidc.issuerUri
    arg_name: issuer-uri
    help_text: |-
      The OIDC issuer URL.
```

Ключ `type:` у флага ОТСУТСТВУЕТ — значение уходит в поле API как строка без разбора и без проверки.

**Положительный контраст, доказывающий, что отсутствие ключа значимо, а не есть промах чтения**
(`05 §I`, «проба обязана различать исходы»): у СОСЕДНЕГО флага того же блока, строки 396–398,
клиентский разбор есть:

```
  oidc_jwks_json_path:
    api_field: workloadIdentityPoolProvider.oidc.jwksJson
    type: "googlecloudsdk.calliope.arg_parsers:FileContents:"
```

То есть в этом же файле, в этом же блоке флагов, механизм клиентской обработки применяется там, где
он нужен, и не применён к `issuer-uri`.

Обратный контроль исправности поиска: `grep -rni "issuer"
lib/googlecloudsdk/command_lib/iam/workload_identity_pools/` даёт ПУСТО при коде возврата 0; тот же
каталог непуст (`__init__.py`, `flags.py`), и `grep -n "def \|Argument" flags.py` в нём печатает
четыре совпадения (`ParseSingleAttributeSelectorArg`, `AddGcpWorkloadSourceFlags`,
`AddUpdateWorkloadSourceFlags` и строку `raise gcloud_exceptions.InvalidArgumentException`).
Инструмент исправен, хуков валидации `issuer-uri` в командной библиотеке IAM нет.

Определение поверхности команды — `lib/surface/iam/workload_identity_pools/providers/create_oidc.yaml`:
флаг подключён ссылкой `_REF_: …flags:workload_identity_pool_provider.oidc_issuer_uri` с
`required: true` и без каких-либо `processor`/`validator`.

**Вывод замера 2:** `gcloud` синтаксис `issuer-uri` ДО отправки на сервер не проверяет вовсе.
Любая проверка — серверная.

## Замер 3 — что о поле говорит сгенерированный клиент API (первичный источник о контракте API)

Источник: `lib/googlecloudsdk/generated_clients/apis/iam/v1/iam_v1_messages.py` — сообщения,
сгенерированные из дискавери-документа `iam/v1`. Наш случай — **workload**-пул (не workforce):
класс с полями `allowedAudiences` / `discoveryUri` / `issuerUri` / `jwksJson`, строки 4455–4487.
Дословно:

```
    issuerUri: Required. The OIDC issuer URL. Must be an HTTPS endpoint. Per
      OpenID Connect Discovery 1.0 spec, the OIDC issuer URL is used to locate
      the provider's public keys (via `jwks_uri`) for verifying tokens like
      the OIDC ID token. These public key types must be 'EC' or 'RSA'.
    jwksJson: Optional. OIDC JWKs in JSON String format. … If
      not set, the `jwks_uri` from the discovery document(fetched from the .well-
      known path of the `issuer_uri`) will be used. …
```

Для сравнения — те же поля у **workforce**-провайдера (строки 640–668), где формулировка требования
жёстче и точнее: «Must be a valid URI using the `https` scheme».

**Что отсюда следует буквально:**

1. Названное требование к значению ровно одно и оно синтаксическое — **HTTPS**. Требования
   «домен должен разрешаться в DNS», «домен должен принадлежать вам», «владение должно быть
   подтверждено» в контракте поля НЕ названы ни в одной из трёх формулировок.
2. Обращение по `issuer_uri` привязано к добыче ключей: «If not set [jwksJson], the `jwks_uri` from
   the discovery document (fetched from the .well-known path of the `issuer_uri`) will be used».
   Условие «if not set» — единственное названное условие обращения.

## Замер 4 — документация платформы: обращение по issuer при загруженных ключах

Страница `cloud.google.com/iam/docs/workload-identity-federation-with-other-providers`
(HTTP 200, 253 976 байт, извлечение текста локальным скриптом). Дословно:

- Раздел с командой создания провайдера, расшифровка подстановки:
  «`JWK_JSON_PATH`: An optional path to a locally uploaded OIDC JWKs. **If this parameter isn't
  supplied, Google Cloud instead uses your IdP's `/.well-known/openid-configuration` path to source
  the JWKs** containing the public keys».
- Раздел «Manage self-uploaded OIDC JWKs (Optional)», подраздел «Delete all uploaded OIDC JWKs»:
  «To delete all of the uploaded OIDC JWKs and **return to using the issuer URI to fetch the keys**,
  run the `gcloud … update-oidc` command with `--jwk-json-path` [указывающим на пустой файл].
  Use the `--issuer-uri` flag to set the issuer URI».

Вторая цитата сильнее первой: платформа сама называет использование issuer-URI для добычи ключей
состоянием, в которое НАДО ВЕРНУТЬСЯ, удалив загруженные ключи. Пока ключи загружены, это состояние
не действует.

Требования к самому токену (та же страница и предыдущий артефакт): `aud` совпадает с URI провайдера
либо со значением из `--allowed-audiences`; `exp` в будущем, `iat` в прошлом, `exp - iat` не больше
24 часов.

---

## Вердикт

**Гипотеза выдерживает проверку документацией и внутренними файлами инструмента, но фактом
о поведении API не становится.**

Что установлено:

1. Единственное НАЗВАННОЕ требование к значению — схема `https`. Требования разрешаемости в DNS и
   подтверждённого владения доменом не названы ни в справке, ни в контракте поля API, ни в
   документации.
2. `gcloud` значение не валидирует вовсе — ни синтаксически, ни семантически (замер 2 с контрастом
   на соседнем флаге).
3. Обращение платформы по `issuer_uri` документировано ровно для случая, когда JWKS НЕ загружен;
   при загруженном JWKS возврат к обращению по issuer требует отдельного действия (удаления
   ключей).

Чего замер НЕ устанавливает и что угадыванию не подлежит:

4. **Примет ли сервер API конкретное значение.** Возможны недокументированные серверные проверки
   (например, отказ на TLD, помеченный как специальный, или попытка резолва при создании). Ни один
   локальный источник этого не различает. **Различающая проверка ровно одна и она прежняя:
   фактическое исполнение `create-oidc` в проекте клиента** — класс B, шаг 5-А пункт 4 брифа
   `T-0-8`. Архитектор её не исполняет и её исход не предсказывает.
5. **Что именно платформа сверяет с claim `iss`.** Требования к `aud`, `iat`, `exp` процитированы;
   отдельной строки «claim `iss` обязан совпадать с `issuer-uri`» ни один из четырёх источников
   дословно не даёт. Это семантика OIDC и допущение брифа (шаг 5-Б п. 3), а не измеренный факт;
   различающая проверка — первый обмен JWT на токен и отрицательный случай того же шага.

## Назначенное значение (вход шага 5-А п. 4, `ADR-051`)

```
https://erp-agent.lombard-ops.invalid
```

Почему именно оно — полностью в `ADR-051`. Коротко: схема `https` (единственное названное
требование выполнено); домен верхнего уровня `.invalid` зарезервирован RFC 6761 §6.4 и в корневую
зону не делегируется никогда, поэтому значение **не может быть зарегистрировано никем** — ни нами,
ни третьей стороной; владения доменом не требует; нового облачного и сетевого ресурса не создаёт;
уникально по имени проекта и роли узла; секретом и endpoint'ом контура клиента не является (не
указывает ни на один живой хост), поэтому `00 §4` не задевает.
