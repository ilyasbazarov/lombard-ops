# T-0-8 · Перемер связности (шаг 1, повтор нужным предикатом) · 2026-08-12

Предмет: проверка того же канала, что и в `reference/T-0-8_agent_channel_measurement_2026-08-12.md`,
но предикатом, соответствующим критерию приёмки — пригодность эндпоинта, а не равенство строки `CN`
строке хоста. Основание перемера — `reference/T-0-8_architect_review_2026-08-12.md`, раздел 1.

Скрипт — `scripts/probe_oauth.ps1`, запущен владельцем по RDP на сервере ERP отдельным процессом
(`powershell -ExecutionPolicy Bypass -File C:\Temp\probe_oauth.ps1`). Вывод перенесён дословно.

## Проба A — список имён сертификата `oauth2.googleapis.com`

```
===== ПРОБА A: список имён (SAN) в сертификате oauth2.googleapis.com =====
SUBJECT : CN=upload.video.google.com
ISSUER  : CN=WE2, O=Google Trust Services, C=US
SAN RAW : DNS-имя=upload.video.google.com, DNS-имя=*.clients.google.com, DNS-имя=*.docs.google.com,
DNS-имя=*.drive.google.com, DNS-имя=*.gdata.youtube.com, DNS-имя=*.googleapis.com,
DNS-имя=*.photos.google.com, DNS-имя=*.youtube-3rd-party.com, DNS-имя=upload.google.com,
DNS-имя=*.upload.google.com, DNS-имя=upload.youtube.com, DNS-имя=*.upload.youtube.com,
DNS-имя=uploads.stage.gdata.youtube.com, DNS-имя=bg-call-donation.goog,
DNS-имя=bg-call-donation-alpha.goog, DNS-имя=bg-call-donation-canary.goog,
DNS-имя=bg-call-donation-dev.goog
СОДЕРЖИТ oauth2.googleapis.com : False
СОДЕРЖИТ *.googleapis.com      : True
```

Разбор строки за строкой:

- `SUBJECT` подтверждает наблюдение прошлого замера — `CN` действительно чужой. Прошлый вердикт
  строился ровно на этой строке.
- `SAN` **предъявлен впервые** и содержит `*.googleapis.com`. Подстановочное имя закрывает ровно
  одну метку слева; `oauth2` — одна метка, значит `oauth2.googleapis.com` этим именем **покрыт**.
- Строка `СОДЕРЖИТ oauth2.googleapis.com : False` ожидаема и вердикта не несёт: точного имени в
  списке нет, покрытие даёт подстановка. Обе строки печатаются намеренно — по одной вывод не
  делается.

## Проба B — обращение к рабочему пути токенного эндпоинта, штатная проверка сертификата

```
===== ПРОБА B: POST на /token со ШТАТНОЙ проверкой сертификата =====
HTTP    : 400
{
  "error": "invalid_request",
  "error_description": "Bad Request"
}
```

Это положительный факт, а не отсутствие ошибки. Проба B исполнялась **в отдельном процессе
PowerShell и без разрешающего обработчика проверки сертификата** — то есть проверку имени вёл
штатный валидатор .NET, и он сертификат **принял**: несовпадение имени дало бы транспортный отказ
без HTTP-кода вовсе, и скрипт напечатал бы ветку `ТРАНСПОРТНЫЙ ОТКАЗ`. Тело ответа — штатная ошибка
Google на заведомо недействительное тело запроса, то есть отвечал именно токенный эндпоинт.

## Вердикт

**Шаг 1 `briefs/T-0-8.md` ПРОЙДЕН. Канал пригоден.**

Обе пробы указывают в одну сторону, ни одна не опирается на отсутствие ошибки:

| Предикат | Чем закрыт |
|---|---|
| Сертификат покрывает запрошенное имя | `*.googleapis.com` в списке имён (проба A) |
| Штатный валидатор имя принимает | HTTP-код есть, транспортного отказа нет (проба B) |
| Эндпоинт отвечает по назначению | Тело ошибки Google на `POST /token` (проба B) |
| Хранилище доступно | Корректный сертификат во всех прогонах прошлого замера |

**Прежний вердикт «не пройдено» — ложноотрицательный.** Причина названа и измерена: проба сравнивала
поле `Subject` с именем хоста, тогда как соответствие определяется списком `subjectAltName`; `CN`
работает только при отсутствии SAN. Гипотеза о перехвате или фильтрации на стороне провайдера,
которая жила в прошлом артефакте как «механизм не установлен», **снята**: механизма нет, потому что
нет и аномалии — фронтенд Google обслуживает `oauth2.googleapis.com` общим сертификатом, чьё главное
имя принадлежит другому сервису того же владельца.

Прошлый артефакт `reference/T-0-8_agent_channel_measurement_2026-08-12.md` **переписыванию не
подлежит** — он датирован и фиксирует, что реально было измерено. Его вердикт отменён здесь и
решением `ADR-048`, а не правкой на месте.

## Остаток, не закрытый этим замером (назван, а не умолчан)

Замерены два эндпоинта: `storage.googleapis.com` и `oauth2.googleapis.com`. Агенту по брифу
понадобится ещё `secretmanager.googleapis.com` — пароль базы лежит в Secret Manager (`05 §II`,
шаг 5 брифа). Он **не измерен**. Это не блокер и не риск канала: имя покрыто той же подстановкой
`*.googleapis.com`, и оба измеренных эндпоинта живы. Но правило «не считать сделанным без лога»
действует, поэтому остаток закрывается внутри `T-0-8` тем же скриптом с заменой значения `$h` —
до первого чтения секрета, а не после.

## Остаток закрыт — `secretmanager.googleapis.com`, 2026-08-12 (`ADR-048`, ПОПРАВКА 1 п.2)

Скрипт — тот же `scripts/probe_oauth.ps1` с `$h = 'secretmanager.googleapis.com'`,
`$path = '/'` (правка внесена в файл скрипта, поведение по умолчанию для `oauth2`/`/token`
не изменилось — см. комментарий в шапке скрипта). Класс B, сервер клиента, отдельная
карточка подтверждения. Прогнал владелец по RDP: `powershell -ExecutionPolicy Bypass
-File C:\Temp\probe_secretmanager.ps1`. Вывод перенесён дословно.

```
===== ПРОБА A: список имён (SAN) в сертификате secretmanager.googleapis.com =====
SUBJECT : CN=upload.video.google.com
ISSUER  : CN=WE2, O=Google Trust Services, C=US
SAN RAW : DNS-имя=upload.video.google.com, DNS-имя=*.clients.google.com, DNS-имя=*.docs.google.com,
DNS-имя=*.drive.google.com, DNS-имя=*.gdata.youtube.com, DNS-имя=*.googleapis.com,
DNS-имя=*.photos.google.com, DNS-имя=*.youtube-3rd-party.com, DNS-имя=upload.google.com,
DNS-имя=*.upload.google.com, DNS-имя=upload.youtube.com, DNS-имя=*.upload.youtube.com,
DNS-имя=uploads.stage.gdata.youtube.com, DNS-имя=bg-call-donation.goog,
DNS-имя=bg-call-donation-alpha.goog, DNS-имя=bg-call-donation-canary.goog,
DNS-имя=bg-call-donation-dev.goog
СОДЕРЖИТ secretmanager.googleapis.com : False
СОДЕРЖИТ *.googleapis.com      : True

===== ПРОБА B: запрос на secretmanager.googleapis.com/ со ШТАТНОЙ проверкой сертификата (без переопределения валидатора) =====
HTTP    : 404
<!DOCTYPE html>... (тело страницы google 404, стандартное для GET / на API-эндпоинте, не транспортная ошибка)
```

**Вердикт — по правилу `ADR-048`: решает штатный механизм (проба B), а не самодельное
сравнение подстроки SAN (проба A).** Проба B выполнялась без переопределения валидатора
сертификата и вернула HTTP-ответ (`404`), а не транспортный отказ — значит цепочка
сертификата и имя хоста `secretmanager.googleapis.com` приняты штатным .NET-валидатором.
`404` на `GET /` для API-эндпоинта Google — ожидаемое тело, не признак сбоя транспорта или
сертификата (тот же класс ответа, что и `400` на `/token` в пробе для `oauth2` выше). Проба A
здесь ровно то же самое, что и для `oauth2.googleapis.com`: сертификат обслуживается по SNI с
чужим `CN` (`upload.video.google.com`), но покрыт тем же `*.googleapis.com` в списке SAN —
диагностика, не вердикт.

**Итог: `secretmanager.googleapis.com` канал пригоден.** Остаток связности, названный в
предыдущем разделе этого файла, закрыт. Все три эндпоинта, нужные агенту
(`storage.googleapis.com`, `oauth2.googleapis.com`, `secretmanager.googleapis.com`), измерены
и живы; условие «провал здесь — стоп и вопрос архитектору» (`ADR-048`, ПОПРАВКА 1 п.2) не
наступило.
