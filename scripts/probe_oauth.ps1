# probe_oauth.ps1 — перемер шага 1 briefs/T-0-8.md нужным предикатом
# Разбор и таблица исходов: reference/T-0-8_architect_review_2026-08-12.md, раздел 5
# Класс B (сервер клиента). Только чтение: ничего не ставит, ничего не пишет, секретов не требует.
# Запуск на сервере ERP:  powershell -ExecutionPolicy Bypass -File C:\Temp\probe_oauth.ps1
#
# Остаток связности `secretmanager.googleapis.com` (ПОПРАВКА 1 briefs/T-0-8.md, п.2, ADR-048):
# тот же скрипт, только $h и $path меняются на секретный эндпоинт —
#   $h    = 'secretmanager.googleapis.com'
#   $path = '/'
# ПРОБА B при этом обязана бить не по хардкоду `/token`, а по `$h$path` — иначе при смене
# $h всё равно бы проверялся токенный эндпоинт, и остаток бы не закрылся. Правка внесена
# ниже; поведение при $h/$path по умолчанию (oauth2, /token) не изменилось.

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$h    = 'oauth2.googleapis.com'
$path = '/token'

'===== ПРОБА A: список имён (SAN) в сертификате ' + $h + ' ====='
try {
    $tcp = New-Object Net.Sockets.TcpClient($h, 443)
    $cb  = [Net.Security.RemoteCertificateValidationCallback] { param($a,$b,$c,$d) $true }
    $ssl = New-Object Net.Security.SslStream($tcp.GetStream(), $false, $cb)
    $ssl.AuthenticateAsClient($h)
    $cert = New-Object Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
    'SUBJECT : ' + $cert.Subject
    'ISSUER  : ' + $cert.Issuer
    $ext = $cert.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.17' }
    if ($null -eq $ext) {
        'SAN     : РАСШИРЕНИЕ ОТСУТСТВУЕТ'
    } else {
        $san = $ext.Format($false)
        $hEscaped = [Text.RegularExpressions.Regex]::Escape($h)
        'SAN RAW : ' + $san
        ('СОДЕРЖИТ ' + $h + ' : ') + [bool]($san -match $hEscaped)
        'СОДЕРЖИТ *.googleapis.com      : ' + [bool]($san -match '\*\.googleapis\.com')
    }
    $ssl.Close(); $tcp.Close()
} catch {
    'ПРОБА A УПАЛА: ' + $_.Exception.Message
}

''
'===== ПРОБА B: запрос на ' + $h + $path + ' со ШТАТНОЙ проверкой сертификата (без переопределения валидатора) ====='
# Метод POST vs GET значения не имеет: цель пробы — получить ЛЮБОЙ HTTP-ответ (пусть даже
# 400/401/404/405) под НЕПОДМЕНЁННЫМ .NET-валидатором сертификата. Любой HTTP-код доказывает,
# что штатная проверка цепочки и имени хоста прошла — при её провале был бы транспортный отказ
# (см. ветку ниже), а не HTTP-ответ. Это ровно та проверка, что различила исходы в ADR-048:
# сравнение самодельным регэкспом (ПРОБА A выше, с переопределённым валидатором) не годится
# как вердикт, годится только как диагностика.
try {
    $body = [Text.Encoding]::ASCII.GetBytes('grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=nonsense')
    $req = [Net.HttpWebRequest]::Create('https://' + $h + $path)
    if ($path -eq '/token') {
        $req.Method        = 'POST'
        $req.ContentType   = 'application/x-www-form-urlencoded'
        $req.ContentLength = $body.Length
        $st = $req.GetRequestStream(); $st.Write($body, 0, $body.Length); $st.Close()
    } else {
        $req.Method = 'GET'
    }
    $resp = $req.GetResponse()
    'HTTP    : ' + [int]$resp.StatusCode
    (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd()
} catch [Net.WebException] {
    if ($null -eq $_.Exception.Response) {
        'ТРАНСПОРТНЫЙ ОТКАЗ (HTTP-ответа нет): ' + $_.Exception.Message
        'STATUS  : ' + $_.Exception.Status
    } else {
        'HTTP    : ' + [int]$_.Exception.Response.StatusCode
        (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd()
    }
}
