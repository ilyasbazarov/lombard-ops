# T-0-8_step6_server_install.ps1 — шаг 6 брифа (ПОПРАВКА 3, ADR-050), КЛАСС B, сервер ERP.
#
# Область: установка кода агента и планировщика на сервер ERP. НЕ включает шаг 7
# (реальный прогон и предъявление) — это отдельная карточка.
#
# Что делает:
#   1) размещает код connector/agent/ в C:\LombardAgent\code\connector\agent
#      (файлы приходят из ОТДЕЛЬНОГО архива, см. carточку — этот скрипт их не
#      скачивает: связность до github.com НЕ измерена ни разу, поэтому код
#      доставляется тем же RDP-каналом, что и сам этот скрипт, не git clone)
#   2) устанавливает зависимости из requirements.txt (python -m pip)
#   3) кладёт файл конфигурации учётных данных (create-cred-config, сгенерирован
#      ЗАРАНЕЕ локально Ilyas — этот скрипт файл не создаёт, только копирует
#      туда, где ему место) в C:\LombardAgent\keys\credentials.json
#   4) выдаёт учётке lombard-agent-svc право "Log on as a batch job"
#      (SeBatchLogonRight) через secedit — SeServiceLogonRight уже выдан
#      РАНЕЕ (заведение учётки), но нужен именно batch logon: пароль учётки
#      сгенерирован случайно и НИГДЕ не хранится, поэтому единственный
#      логон-тип планировщика, не требующий пароля, — S4U, а S4U требует
#      именно SeBatchLogonRight (справка платформы; ЭТО НЕ факт о сервере
#      клиента, а документированное поведение Task Scheduler — проверяется
#      локально `Get-Help New-ScheduledTaskPrincipal -Full` при сомнении)
#   5) создаёт задачу планировщика с LogonType S4U под lombard-agent-svc,
#      ежедневным триггером и нужными переменными окружения в самой команде
#      запуска (не в системном PATH — не палить общие переменные сервера)
#
# НЕ исполнять без отдельного подтверждения Ilyas по карточке. Печатает
# сделанное, не молчит (тот же стиль, что и step5b). Пароль учётки, приватный
# ключ, значение секрета базы — нигде не печатаются и не запрашиваются этим
# скриптом.
#
# Параметры без значений по умолчанию — ЗАВЕДЕНЫ ЯВНО, не подставляются:
#   -SourceArchive       путь к ZIP с кодом connector/agent/ (см. карточку —
#                        способ доставки на сервер: RDP + notepad, base64 одним
#                        куском, см. текст карточки в сессии, не в этом файле)
#   -CredentialConfigSrc путь к credentials.json, сгенерированному ЛОКАЛЬНО
#                        (create-cred-config), уже скопированному на сервер
#                        рядом с этим скриптом
#
# Запуск:
#   powershell -ExecutionPolicy Bypass -File T-0-8_step6_server_install.ps1 `
#       -SourceArchive "C:\Temp\connector_agent.zip" `
#       -CredentialConfigSrc "C:\Temp\credentials.json"

param(
    [Parameter(Mandatory = $true)]
    [string]$SourceArchive,

    [Parameter(Mandatory = $true)]
    [string]$CredentialConfigSrc,

    [string]$ServiceAccountName = "lombard-agent-svc",

    [string]$CodeDir = "C:\LombardAgent\code",

    [string]$KeyDir = "C:\LombardAgent\keys",

    [string]$TaskName = "LombardAgentDailyRun",

    [string]$DailyTime = "03:00"
)

$ErrorActionPreference = 'Stop'

'##### T-0-8 / шаг 6 — установка кода, зависимостей, конфигурации учётных данных, планировщика #####'
'ЛОКАЛЬНОЕ ВРЕМЯ ЗАПУСКА : ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss K')
'СЛУЖЕБНАЯ УЧЁТКА : ' + $ServiceAccountName
'КАТАЛОГ КОДА : ' + $CodeDir
'ИМЯ ЗАДАЧИ ПЛАНИРОВЩИКА : ' + $TaskName
''

# ============================================================================
# 1. КОД АГЕНТА — распаковка ZIP, доставленного отдельно по RDP (не git clone:
#    связность до github.com не измерена этим брифом ни разу)
# ============================================================================
'===== 1. КОД АГЕНТА ====='
if (-not (Test-Path $SourceArchive)) {
    'ИСХОДНЫЙ АРХИВ НЕ НАЙДЕН: ' + $SourceArchive + ' — скопируйте его на сервер ДО запуска этого скрипта.'
    exit 1
}
New-Item -ItemType Directory -Force -Path $CodeDir | Out-Null
Expand-Archive -Path $SourceArchive -DestinationPath $CodeDir -Force
'РАСПАКОВАНО В : ' + $CodeDir
'СОДЕРЖИМОЕ (connector\agent):'
Get-ChildItem (Join-Path $CodeDir "connector\agent") -Name
''

# ============================================================================
# 2. ЗАВИСИМОСТИ — requirements.txt агента
# ============================================================================
'===== 2. ЗАВИСИМОСТИ (pip) ====='
$reqPath = Join-Path $CodeDir "connector\agent\requirements.txt"
if (-not (Test-Path $reqPath)) {
    'requirements.txt НЕ НАЙДЕН ПО ПУТИ ' + $reqPath + ' — установка зависимостей прервана.'
    exit 1
}
'requirements.txt:'
Get-Content $reqPath
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r $reqPath
if ($LASTEXITCODE -ne 0) {
    'УСТАНОВКА ЗАВИСИМОСТЕЙ УПАЛА (код ' + $LASTEXITCODE + ') — дальше не идём.'
    exit 1
}
'ЗАВИСИМОСТИ УСТАНОВЛЕНЫ. Список pip после установки (для артефакта):'
python -m pip freeze
''

# ============================================================================
# 3. ФАЙЛ КОНФИГУРАЦИИ УЧЁТНЫХ ДАННЫХ (create-cred-config) — копирование
#    (генерация этого файла ЗДЕСЬ НЕ ПРОИСХОДИТ: он сгенерирован ЛОКАЛЬНО
#    штатной командой gcloud, этот скрипт только кладёт его на место)
# ============================================================================
'===== 3. КОНФИГУРАЦИЯ УЧЁТНЫХ ДАННЫХ ====='
if (-not (Test-Path $CredentialConfigSrc)) {
    'ФАЙЛ КОНФИГУРАЦИИ НЕ НАЙДЕН: ' + $CredentialConfigSrc + ' — скопируйте его на сервер ДО запуска (сгенерирован локально create-cred-config).'
    exit 1
}
New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null
$credentialConfigDst = Join-Path $KeyDir "credentials.json"
Copy-Item -Path $CredentialConfigSrc -Destination $credentialConfigDst -Force
'СКОПИРОВАН В : ' + $credentialConfigDst + ' (не секрет: JSON не несёт приватного ключа, только имя провайдера, путь к файлу с JWT и SA для олицетворения — но не для общего чтения, права ограничиваем ниже так же, как ключ)'
icacls $credentialConfigDst /inheritance:r
icacls $credentialConfigDst /grant:r ("$env:COMPUTERNAME\" + $ServiceAccountName + ":(R)")
icacls $credentialConfigDst /grant:r "SYSTEM:(F)"
'ПРАВА ПОСЛЕ ОГРАНИЧЕНИЯ:'
icacls $credentialConfigDst
''

# ============================================================================
# 4. ПРАВО "Log on as a batch job" (SeBatchLogonRight) — нужно для S4U
#    (SeServiceLogonRight уже выдан заведением учётки, но S4U — другой логон-тип)
# ============================================================================
'===== 4. ПРАВО SeBatchLogonRight (secedit) ====='
$sid = (New-Object System.Security.Principal.NTAccount($ServiceAccountName)).Translate([System.Security.Principal.SecurityIdentifier]).Value
'SID ' + $ServiceAccountName + ' : ' + $sid

$seceditDbPath = Join-Path $env:TEMP "t0_8_step6_secedit.sdb"
$seceditCfgExport = Join-Path $env:TEMP "t0_8_step6_secedit_export.inf"
$seceditCfgImport = Join-Path $env:TEMP "t0_8_step6_secedit_import.inf"

secedit /export /cfg $seceditCfgExport /areas USER_RIGHTS | Out-Null
if (-not (Test-Path $seceditCfgExport)) {
    'secedit /export НЕ СОЗДАЛ ФАЙЛ — право не выдано, дальше не идём.'
    exit 1
}

$exportedLines = Get-Content $seceditCfgExport
$batchLine = $exportedLines | Where-Object { $_ -match '^SeBatchLogonRight' }
if ($batchLine -and $batchLine -match [Regex]::Escape($sid)) {
    'SeBatchLogonRight УЖЕ НЕСЁТ SID ' + $sid + ' — повторно не выдаём (идемпотентно):'
    $batchLine
} else {
    if ($batchLine) {
        $newLine = $batchLine.TrimEnd() + ',*' + $sid
    } else {
        $newLine = 'SeBatchLogonRight = *' + $sid
    }
    $newLines = @()
    $replaced = $false
    foreach ($line in $exportedLines) {
        if ($line -match '^SeBatchLogonRight') {
            $newLines += $newLine
            $replaced = $true
        } else {
            $newLines += $line
        }
    }
    if (-not $replaced) {
        # Строки SeBatchLogonRight не было вовсе — добавляем в секцию [Privilege Rights]
        $out = @()
        foreach ($line in $newLines) {
            $out += $line
            if ($line -match '^\[Privilege Rights\]') {
                $out += $newLine
            }
        }
        $newLines = $out
    }
    [System.IO.File]::WriteAllLines($seceditCfgImport, $newLines, (New-Object System.Text.UTF8Encoding($false)))
    'ПРИМЕНЕНИЕ (secedit /configure):'
    secedit /configure /db $seceditDbPath /cfg $seceditCfgImport /areas USER_RIGHTS
    if ($LASTEXITCODE -ne 0) {
        'secedit /configure ВЕРНУЛ КОД ' + $LASTEXITCODE + ' — право НЕ выдано, дальше не идём.'
        exit 1
    }
}
'ПРОВЕРКА ПОСЛЕ ПРИМЕНЕНИЯ (secedit /export повторно):'
secedit /export /cfg $seceditCfgExport /areas USER_RIGHTS | Out-Null
(Get-Content $seceditCfgExport) | Where-Object { $_ -match '^SeBatchLogonRight' }
Remove-Item $seceditCfgExport, $seceditCfgImport, $seceditDbPath -Force -ErrorAction SilentlyContinue
''

# ============================================================================
# 5. ЗАДАЧА ПЛАНИРОВЩИКА — LogonType S4U (без пароля), ежедневно
# ============================================================================
'===== 5. ЗАДАЧА ПЛАНИРОВЩИКА (S4U, ежедневно ' + $DailyTime + ') ====='

$pythonCmd = (Get-Command python).Source
$runDailyPath = Join-Path $CodeDir "connector\agent\run_daily.py"

# Переменные окружения задачи — в АРГУМЕНТАХ команды запуска, не в системном
# PATH/переменных сервера (не палить общие переменные сервера, требование
# сессии). PowerShell-обёртка выставляет их только для дочернего процесса.
$envSetupLines = @(
    '$env:PROJECT_ID = "project-c451b48a-07ae-4de4-961"',
    '$env:LOMBARD_AGENT_ISSUER_URI = "https://erp-agent.lombard-ops.invalid"',
    '$env:LOMBARD_AGENT_SUBJECT = "lombard-agent-erp01"',
    '$env:LOMBARD_AGENT_AUDIENCE = "//iam.googleapis.com/projects/450925595005/locations/global/workloadIdentityPools/lombard-agent-federation-pool/providers/lombard-agent-jwt-provider"',
    '$env:LOMBARD_AGENT_PRIVATE_KEY_PATH = "' + (Join-Path $KeyDir "private_key.pem") + '"',
    '$env:LOMBARD_AGENT_KID = "lombard-agent-20260813"',
    '$env:LOMBARD_AGENT_CREDENTIAL_SOURCE_FILE = "' + (Join-Path $KeyDir "signed_jwt.txt") + '"',
    '$env:GOOGLE_APPLICATION_CREDENTIALS = "' + $credentialConfigDst + '"'
)
$wrapperPath = Join-Path $CodeDir "run_daily_wrapper.ps1"
$wrapperBody = @"
`$ErrorActionPreference = 'Stop'
$($envSetupLines -join "`r`n")
# LOMBARD_DB_CHARSET — CONTEXT GAP этой сессии: кодировка подключения Firebird
# не названа НИГДЕ в репозитории и не подставляется угадыванием
# (anti-improvisation). Замените строку ниже реальным значением ДО первого
# прогона задачи (шаг 7, отдельная карточка) — до тех пор запуск отбивается
# явной ошибкой, а не тихим падением внутри Python.
`$env:LOMBARD_DB_CHARSET = ""
if (-not `$env:LOMBARD_DB_CHARSET) {
    Write-Error 'CONTEXT GAP: LOMBARD_DB_CHARSET не задан — впишите реальную кодировку подключения Firebird в этот файл (строка выше) ДО первого прогона. Не подставляется наугад.'
    exit 2
}
& "$pythonCmd" "$runDailyPath"
exit `$LASTEXITCODE
"@
[System.IO.File]::WriteAllText($wrapperPath, $wrapperBody, (New-Object System.Text.UTF8Encoding($false)))
'ОБЁРТКА ЗАПУСКА СОЗДАНА : ' + $wrapperPath
'СОДЕРЖИМОЕ (переменные окружения — значения, не секреты; пароль базы сюда не идёт, он берётся из Secret Manager внутри run_daily.py):'
Get-Content $wrapperPath
'ВНИМАНИЕ: LOMBARD_DB_CHARSET — CONTEXT GAP, не подставлен угадыванием. Впишите реальное значение в файл ' + $wrapperPath + ' ДО первого прогона задачи (шаг 7, отдельная карточка).'
''

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    'ЗАДАЧА ' + $TaskName + ' УЖЕ СУЩЕСТВУЕТ — удаляется перед пересозданием (идемпотентность):'
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $wrapperPath + '"')
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyTime
$principal = New-ScheduledTaskPrincipal -UserId ("$env:COMPUTERNAME\" + $ServiceAccountName) `
    -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Description "T-0-8: ежедневная выгрузка PawnShop -> GCS (ADR-050)" | Out-Null

'ЗАДАЧА СОЗДАНА. Проверка (Get-ScheduledTask):'
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
'Проверка принципала (LogonType обязан быть S4U — предъявляется выводом, не утверждением):'
(Get-ScheduledTask -TaskName $TaskName).Principal | Format-List UserId, LogonType, RunLevel
''

'##### ГОТОВО. Задача НЕ запущена этим скриптом — реальный прогон и предъявление #####'
'##### остаются шагом 7 брифа T-0-8, отдельная карточка. #####'
'Что предъявить в артефакте шага 6:'
'- содержимое connector\agent на сервере (Get-ChildItem)'
'- вывод pip freeze'
'- права icacls на credentials.json'
'- вывод secedit /export по SeBatchLogonRight (SID учётки присутствует)'
'- вывод Get-ScheduledTask / Principal (LogonType: S4U)'
'ПАРОЛЬ УЧЁТКИ, ПРИВАТНЫЙ КЛЮЧ, ПАРОЛЬ БАЗЫ В ЭТОТ ВЫВОД НЕ ПОПАЛИ НИГДЕ.'
