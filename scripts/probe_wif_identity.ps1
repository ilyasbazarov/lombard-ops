# probe_wif_identity.ps1 — замер на сервере ERP: какой механизм workload identity federation
# применим (Q-21, вариант 2). Основание — разбор Q-21 в 07_GAPS.md от 2026-08-13.
#
# Класс B (сервер клиента). ТОЛЬКО ЧТЕНИЕ: ничего не устанавливает, ни одного файла не создаёт
# и не меняет, ни одной службы не трогает, к БД PawnShop не обращается вовсе, секретов не читает
# и не печатает. Ключевая пара в разделе 3 создаётся В ПАМЯТИ и уничтожается там же
# (PersistKeyInCsp = $false + Clear()) — на диск не попадает ничего.
#
# Запуск на сервере ERP:  powershell -ExecutionPolicy Bypass -File C:\Temp\probe_wif_identity.ps1
# Доставка файла — по практике RDP из 10_GCP_INFRA_PLAYBOOK (notepad + вставка правым кликом).
#
# Правило вердикта (ADR-048): там, где предикат уже реализован штатным механизмом платформы,
# меряет он, а не самодельное сравнение строк. Поэтому связность в разделе 6 проверяется
# НЕПОДМЕНЁННЫМ валидатором .NET: любой HTTP-код доказывает, что цепочка и имя хоста приняты.
# Пустая выдача при нулевом коде возврата фактом «нет данных» НЕ является (05 §I) — каждая
# ветка печатает либо найденное, либо дословный текст отказа.

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

'##### T-0-8 / Q-21 — пригодность сервера как источника федерации. Только чтение. #####'
'ЛОКАЛЬНОЕ ВРЕМЯ ЗАПУСКА : ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss K')
''

'===== 1. МАШИНА: домен или рабочая группа =====' 
try {
    $cs = Get-CimInstance Win32_ComputerSystem
    'ИМЯ            : ' + $cs.Name
    'В ДОМЕНЕ       : ' + $cs.PartOfDomain
    'ДОМЕН/ГРУППА   : ' + $cs.Domain
    'DomainRole     : ' + $cs.DomainRole + '  (0/1 = рабочая станция, 2/3 = рядовой сервер, 4/5 = контроллер домена)'
    $os = Get-CimInstance Win32_OperatingSystem
    'ОС             : ' + $os.Caption + ' build ' + $os.BuildNumber
    'ProductType    : ' + (Get-CimInstance Win32_OperatingSystem).ProductType + '  (1 = рабочая станция, 2 = контроллер домена, 3 = сервер)'
} catch {
    'РАЗДЕЛ 1 УПАЛ  : ' + $_.Exception.Message
}
''

'===== 2. ЕСТЬ ЛИ КОРПОРАТИВНЫЙ ПОСТАВЩИК ИДЕНТИЧНОСТИ (роли и службы) ====='
'--- 2.1 Роли Windows Server ---'
try {
    Import-Module ServerManager -ErrorAction Stop
    $feat = Get-WindowsFeature ADFS-Federation, AD-Domain-Services, Web-Server, Windows-Identity-Foundation -ErrorAction Stop
    if ($null -eq $feat) {
        'Get-WindowsFeature вернул пусто — это ГЭП НАБЛЮДЕНИЯ, а не «ролей нет»'
    } else {
        $feat | Format-Table Name, InstallState, DisplayName -AutoSize | Out-String
    }
} catch {
    'Get-WindowsFeature НЕДОСТУПЕН (модуль ServerManager): ' + $_.Exception.Message
    'Ниже — независимая проверка тем же предметом через список служб (раздел 2.2).'
}
'--- 2.2 Службы, по которым узнаётся AD FS / AD DS / Azure AD Connect ---'
$svcNames = @('adfssrv','drs','ADWS','NTDS','Kdc','ADSync','AzureADConnectHealthSync')
foreach ($n in $svcNames) {
    $s = Get-Service -Name $n -ErrorAction SilentlyContinue
    if ($null -eq $s) {
        'СЛУЖБА ' + $n.PadRight(26) + ' : НЕ ЗАРЕГИСТРИРОВАНА'
    } else {
        'СЛУЖБА ' + $n.PadRight(26) + ' : есть, статус ' + $s.Status + ', запуск ' + $s.StartType
    }
}
'--- 2.3 Установленное ПО, имя которого содержит признак федерации ---'
try {
    $keys = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
              'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')
    $hits = Get-ItemProperty $keys -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -match 'ADFS|AD FS|Azure AD|Entra|Federation|Keycloak|Okta|Shibboleth' } |
            Select-Object DisplayName, DisplayVersion
    if ($null -eq $hits -or $hits.Count -eq 0) {
        'Совпадений по признакам федерации в списке установленного ПО НЕТ (обратный контроль ниже).'
        $ctrl = (Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName }).Count
        'ОБРАТНЫЙ КОНТРОЛЬ: всего записей с DisplayName прочитано — ' + $ctrl + ' (ноль здесь означал бы неисправность пробы, а не отсутствие ПО)'
    } else {
        $hits | Format-Table -AutoSize | Out-String
    }
} catch {
    'РАЗДЕЛ 2.3 УПАЛ : ' + $_.Exception.Message
}
''

'===== 3. МОЖЕМ ЛИ МЫ САМИ ПОДПИСЫВАТЬ JWT (путь «самоподписанный OIDC») ====='
'PSVersion      : ' + $PSVersionTable.PSVersion.ToString()
'CLRVersion     : ' + $PSVersionTable.CLRVersion
try {
    $ndp = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full' -ErrorAction Stop
    '.NET Framework : Release ' + $ndp.Release + ', Version ' + $ndp.Version
} catch {
    '.NET Framework : ключ NDP\v4\Full не прочитан — ' + $_.Exception.Message
}
$rsa = $null
try {
    $rsa = New-Object Security.Cryptography.RSACryptoServiceProvider(2048)
    $rsa.PersistKeyInCsp = $false      # ключ НЕ сохраняется в контейнер CSP: замер не оставляет следов
    'RSA 2048 в памяти : создан, KeySize = ' + $rsa.KeySize
    $data = [Text.Encoding]::UTF8.GetBytes('lombard-ops probe')
    $sig  = $rsa.SignData($data, [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
    'ПОДПИСЬ RS256     : получена, длина ' + $sig.Length + ' байт'
    $ok = $rsa.VerifyData($data, $sig, [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
    'ПРОВЕРКА ПОДПИСИ  : ' + $ok
    $p = $rsa.ExportParameters($false)
    'ЭКСПОРТ ОТКРЫТОЙ ЧАСТИ (нужна для JWKS): modulus ' + $p.Modulus.Length + ' байт, exponent ' + $p.Exponent.Length + ' байт'
} catch {
    'КРИПТО-ПРОБА УПАЛА: ' + $_.Exception.Message
    'Это ОТРИЦАТЕЛЬНЫЙ факт именно той проверки, которую мерили: подписать JWT штатным .NET на этой машине не удалось.'
} finally {
    if ($null -ne $rsa) { $rsa.Clear() }
}
''

'===== 4. PYTHON (агент T-0-8 написан на Python; федеративные креды отдаёт та же библиотека) ====='
$py = (& cmd.exe /c "where python 2>&1")
'where python   : ' + ($py -join ' | ')
$py3 = (& cmd.exe /c "where python3 2>&1")
'where python3  : ' + ($py3 -join ' | ')
$pyl = (& cmd.exe /c "py -0p 2>&1")
'py -0p         : ' + ($pyl -join ' | ')
try {
    $v = (& cmd.exe /c "python --version 2>&1")
    'python --version : ' + ($v -join ' | ')
} catch {
    'python --version : не запустился — ' + $_.Exception.Message
}
''

'===== 5. ЧАСЫ (подписанный JWT с расхождением часов отвергается на стороне Google) ====='
'UTC СЕЙЧАС     : ' + ([DateTime]::UtcNow).ToString('yyyy-MM-dd HH:mm:ss')
'ЧАСОВОЙ ПОЯС   : ' + (Get-TimeZone).Id
$w32 = (& cmd.exe /c "w32tm /query /status 2>&1")
'w32tm /query /status :'
$w32 | ForEach-Object { '   ' + $_ }
''

'===== 6. СВЯЗНОСТЬ К ЭНДПОИНТАМ ФЕДЕРАЦИИ (шагом 1 НЕ мерились) ====='
'Предикат ADR-048: вердикт даёт ШТАТНЫЙ валидатор .NET. Любой HTTP-код = цепочка и имя приняты.'
foreach ($h in @('sts.googleapis.com','iamcredentials.googleapis.com')) {
    ''
    '--- ' + $h + ' (GET https://' + $h + '/) ---'
    try {
        $req = [Net.HttpWebRequest]::Create('https://' + $h + '/')
        $req.Method  = 'GET'
        $req.Timeout = 20000
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
    } catch {
        'НЕОЖИДАННЫЙ ОТКАЗ: ' + $_.Exception.Message
    }
}
''
'##### КОНЕЦ ЗАМЕРА. Вывод возвращать ЦЕЛИКОМ, включая строки отказов. #####'
