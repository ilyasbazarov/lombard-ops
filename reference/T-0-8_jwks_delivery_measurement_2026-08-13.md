# T-0-8 · Замер способа доставки JWKS в Workload Identity Pool Provider · 2026-08-13

Предмет: закрыть вопрос «(а) где публикуется JWKS» из `Q-21` — обязателен ли публично читаемый
issuer-URL (то есть НОВЫЙ публичный бакет, отдельный облачный ресурс и отдельное решение
владельца), или открытые ключи передаются провайдеру напрямую при создании.

Основание — `07_GAPS.md`, строка `Q-21`: «либо JWKS передаётся провайдеру напрямую при его
создании (это внешнее знание о платформе, то есть гипотеза `ADR-045`; проверяется печатью `--help`
команды создания OIDC-провайдера — вывод справки, ни одного объекта не касается)».

Класс A. Печать справки установленного локально `gcloud` и чтение официальной документации
платформы. Ни одного облачного объекта не создано, не изменено и не прочитано; ни одной команды
на проект клиента не отправлено; аутентификация не требовалась.

## Замер 1 — справка команды создания OIDC-провайдера (локально, дословно)

Инструмент: `Google Cloud SDK 577.0.0`, `core 2026.07.17` (вывод `gcloud version`).
Команда: `gcloud iam workload-identity-pools providers create-oidc --help`.

Секция `SYNOPSIS` дословно:

```
gcloud iam workload-identity-pools providers create-oidc
    (PROVIDER : --location=LOCATION
      --workload-identity-pool=WORKLOAD_IDENTITY_POOL)
    --attribute-mapping=[KEY=VALUE,...] --issuer-uri=ISSUER_URI
    [--allowed-audiences=[ALLOWED_AUDIENCES,...]]
    [--attribute-condition=ATTRIBUTE_CONDITION] [--description=DESCRIPTION]
    [--disabled] [--display-name=DISPLAY_NAME]
    [--jwk-json-path=PATH_TO_FILE] [GCLOUD_WIDE_FLAG ...]
```

Секция `OPTIONAL FLAGS`, флаг `--jwk-json-path`, дословно:

```
 --jwk-json-path=PATH_TO_FILE
    Optional file containing jwk public keys. The file format must follow
    jwk specifications (https://www.rfc-editor.org/rfc/rfc7517#section-4).
    Example file format:            {
          "keys": [
             {
                  "kty": "RSA/EC",
                  "alg": "<algorithm>",
                  "use": "sig",
                  "kid": "<key-id>",
                  "n": "",
                  "e": "",
                  "x": "",
                  "y": "",
                  "crv": ""
             }
          ]
        }
    . Use a full or relative path to a local file containing the value of
    jwk_json_path.
```

Пример из секции `EXAMPLES` той же справки содержит `--jwk-json-path="path/to/jwk.json"` рядом с
`--issuer-uri="https://test-idp.com"` — то есть флаги применяются ВМЕСТЕ, а не исключают друг друга.

Секция `API REFERENCE` той же справки: «This command uses the iam/v1 API».

## Замер 2 — тот же флаг у команды ОБНОВЛЕНИЯ провайдера (ротация)

Команда: `gcloud iam workload-identity-pools providers update-oidc --help`.
Флаг `--jwk-json-path=PATH_TO_FILE` присутствует в `SYNOPSIS` (строка 13 вывода) и в
`OPTIONAL FLAGS` (строка 208) с тем же дословным описанием, что и у `create-oidc`.

Значение факта: ротация открытых ключей исполняется тем же механизмом, что и первичная загрузка, —
обновлением провайдера, без внешнего URL и без публикации чего-либо наружу.

## Замер 3 — команда генерации конфигурации учётных данных

Команда: `gcloud iam workload-identity-pools create-cred-config --help`.
`SYNOPSIS` перечисляет взаимоисключающую группу источников субъектного токена:
`(--aws | --azure | --credential-cert-path | --credential-source-file | --credential-source-url |
--executable-command)`, плюс `--service-account=SERVICE_ACCOUNT` и `--output-file=OUTPUT_FILE`.

Пример из `EXAMPLES` дословно:

```
$ gcloud iam workload-identity-pools create-cred-config \
    projects/$PROJECT_NUMBER/locations/$REGION/\
workloadIdentityPools/$WORKLOAD_POOL_ID/providers/$PROVIDER_ID \
    --service-account=$EMAIL \
    --credential-source-file=$PATH_TO_OIDC_ID_TOKEN \
    --output-file=credentials.json
```

Значение факта: файл конфигурации учётных данных ГЕНЕРИРУЕТСЯ штатной командой платформы, а не
пишется нами по памяти (`ADR-048`: там, где предикат уже реализован штатным механизмом, идём им).

## Внешний источник — официальная документация платформы

Страница `iam/docs/workload-identity-federation-with-other-providers` (раздел о доступе к JWKS).
Приводится как **источник о платформе Google, а не о контуре клиента**: разрез `ADR-045` («внешний
источник — гипотеза, не факт») адресует утверждения о СИСТЕМЕ КЛИЕНТА; здесь предметом является
сама платформа, а её собственная документация и её собственный инструмент — первичный источник.

Цитаты (дословно, из выдачи фетча):

- «Google Cloud downloads OIDC metadata from the IdP, through a publicly available, well-known,
  internet-accessible discovery URL».
- «You can upload an OIDC JWKS file directly to Google Cloud when you create or update the OIDC
  workload identity pool provider».
- «You can use this method when the IdP's OIDC metadata endpoint URL isn't publicly accessible.
  A maximum of 8 keys can be uploaded to Google Cloud».
- «if a JWK file (JSON) is not supplied, Google Cloud attempts to fetch a JWK from the issuer».

Требования к токену (та же страница): claim `aud` совпадает с URI провайдера; `exp` в будущем,
`iat` в прошлом; «The value of `exp` must be greater than the value of `iat` by at most 24 hours».

## Вердикт

**Публично читаемый issuer-URL НЕ обязателен.** Открытые ключи (JWKS) передаются провайдеру
напрямую при создании (`--jwk-json-path`) и обновляются тем же флагом у `update-oidc`. Загрузка
ключей и есть штатный, документированный платформой способ для случая «эндпоинт метаданных IdP не
доступен публично» — ровно наш случай. Потолок — 8 ключей, чего с запасом хватает на схему ротации
с перекрытием двух.

**Новый публичный бакет не заводится.** Развилка «новый публичный бакет либо передача напрямую»
закрыта в пользу передачи напрямую; вопрос об отдельном облачном ресурсе и отдельном решении
владельца о его заведении СНИМАЕТСЯ, а не обходится: анонимно читаемого объекта в контуре клиента
не появляется вовсе. Три бакета `T-0-7` с `public_access_prevention: enforced` остаются как есть;
обхода их закрытости не предлагается и не требуется.

**Что этим замером НЕ установлено** (и угадыванию не подлежит):

1. **Примет ли API значение `--issuer-uri`, которое не разрешается в сети.** Флаг остаётся
   ОБЯЗАТЕЛЬНЫМ (`REQUIRED FLAGS` справки) при любом способе доставки ключей: он задаёт значение,
   с которым сверяется claim `iss` токена. Документация не требует его достижимости при загруженных
   ключах, и цитата «if a JWK file (JSON) is not supplied, Google Cloud attempts to fetch a JWK
   from the issuer» читается как «при поданном файле не обращается», — но это чтение, а не замер.
   Различающая проверка — единственная: фактическое создание провайдера. Она класс B и входит в
   шаг 5-А, а не в этот замер.
2. **Действующие на проекте политики организации, кроме двух уже измеренных.** В частности
   `constraints/iam.allowedPolicyMemberDomains` (ограничение доменов в IAM-политиках) не
   измерялся ни разу. Если он enforced, он способен отбить выдачу роли `roles/iam.workloadIdentityUser`
   на внешний principal — это ровно тот класс неизмеренного ограничения, который снял шаг 5
   (`ADR-049`). Замер — одна read-only команда, входит в карточку шага 5-А.
3. **Поведение STS при рассинхронизации часов сервера.** Служба времени Windows на сервере ERP не
   запущена (замер `reference/T-0-8_server_identity_measurement_2026-08-13.md`, раздел 5), а
   требования к `iat`/`exp` процитированы выше. Это не гипотеза о платформе, а известная
   зависимость: она уходит в шаг 5-Б условием, а не пожеланием.
