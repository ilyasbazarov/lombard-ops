param(
    [string]$Queries = "",
    [string]$IdFields = ""
)

# scripts/T-0-6_run_discovery.ps1 — обёртка запуска на сервере ERP, бриф T-0-6
# (шаги 3+, класс B). Устройство дословно повторяет `T-0-4a_run_discovery.ps1`
# (тот же образец — брифом велено читать его как образец устройства модуля
# замера и оффлайн-теста): один и тот же файл вызывается НЕСКОЛЬКО раз в ходе
# задачи — каждый вызов исполняет СВОЙ список запросов, соответствующий ровно
# ОДНОМУ шагу брифа (05_CONVENTIONS §I, «один скрипт на шаг, а не на команду»),
# и каждый такой вызов требует своей отдельной карточки подтверждения владельца
# ПЕРЕД запуском.
#
# **Источник списка запросов — ДВА способа**, тот же приём, что T-0-4a:
# `-Queries` явным текстом — для разового/ручного вызова; если НЕ передан
# (пустая строка по умолчанию) — `discovery_t0_6.py` сам читает список из
# control-файла (по умолчанию `C:\LombardAgent\control\t0_6_next_queries.txt`,
# см. `DEFAULT_QUERIES_FILE` в модуле). Причина — `schtasks /change /tr` для
# password-based задачи планировщика требует пароль учётки заново при КАЖДОЙ
# смене `/tr` (измерено `T-0-4a`, 2026-08-18, реальное ограничение платформы).
# `-IdFields` — тот же приём для ID_FIELD марки/модели/года/госномера,
# найденных запросом `vehicle_field_candidates` шага 8; НЕОБЯЗАТЕЛЕН.
#
# ТРЕБУЕТСЯ запуск от имени `lombard-agent-svc` (Задача планировщика Windows,
# по образцу `LombardAgentDailyRun`/`LombardAgentDiscoveryT0-4a` —
# `11_INFRA_FACTS.md`, «Способ запуска агента»), НЕ прямой интерактивный запуск
# из RDP-сессии администратора — `icacls` на `C:\LombardAgent\keys\private_key.pem`
# даёt чтение ТОЛЬКО этой учётке и `NT AUTHORITY\СИСТЕМА` (замер шага 4 `T-0-4a`).
#
# Переменные окружения ниже — публикуемые факты (`11_INFRA_FACTS.md`, `ADR-051`),
# не секреты: тот же набор, что уже используют `scripts/T-0-8_step7_*_wrapper*.ps1`
# и `scripts/T-0-4a_run_discovery.ps1` на этом сервере. Пароль LOMBARD_RO и
# приватный ключ подписи в этот файл не попадают.

$ErrorActionPreference = 'Stop'
$env:Path = "C:\LombardAgent\firebird-client64;" + $env:Path
$env:PROJECT_ID = "project-c451b48a-07ae-4de4-961"
$env:LOMBARD_AGENT_ISSUER_URI = "https://erp-agent.lombard-ops.invalid"
$env:LOMBARD_AGENT_SUBJECT = "lombard-agent-erp01"
$env:LOMBARD_AGENT_AUDIENCE = "//iam.googleapis.com/projects/450925595005/locations/global/workloadIdentityPools/lombard-agent-federation-pool/providers/lombard-agent-jwt-provider"
$env:LOMBARD_AGENT_PRIVATE_KEY_PATH = "C:\LombardAgent\keys\private_key.pem"
$env:LOMBARD_AGENT_KID = "lombard-agent-20260813"
$env:LOMBARD_AGENT_CREDENTIAL_SOURCE_FILE = "C:\LombardAgent\keys\signed_jwt.txt"
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\LombardAgent\keys\credentials.json"
$env:LOMBARD_DB_CHARSET = "WIN1251"
if (-not $env:LOMBARD_DB_CHARSET) {
    Write-Error 'CONTEXT GAP: LOMBARD_DB_CHARSET ne zadan - zapusk nevozmozhen bez parametra podklyucheniya k Firebird.'
    exit 2
}

$logDir = "C:\LombardAgent\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutFile = Join-Path $logDir ("t0_6_discovery_{0}.out.log" -f $stamp)
$stderrFile = Join-Path $logDir ("t0_6_discovery_{0}.err.log" -f $stamp)

$scriptArgs = @(
    '"C:\LombardAgent\code\connector\agent\discovery_t0_6.py"'
)
if ($Queries -ne "") {
    # Явный -Queries — старый способ, побеждает control-файл.
    $scriptArgs += @('--queries', $Queries)
}
# Иначе флаг --queries не передаётся вовсе — discovery_t0_6.py читает
# DEFAULT_QUERIES_FILE сам; отсутствие/пустота файла отбивается ЕГО
# собственным CONTEXT GAP (DiscoveryConfigError), не этим скриптом.
if ($IdFields -ne "") {
    $scriptArgs += @('--id-fields', $IdFields)
}

$proc = Start-Process -FilePath "C:\Program Files\Python314\python.exe" -ArgumentList $scriptArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
Add-Content -Path $stdoutFile -Value ("EXITCODE: {0}" -f $proc.ExitCode)
Add-Content -Path $stdoutFile -Value ("QUERIES ARG: {0}" -f $(if ($Queries -ne "") { $Queries } else { "(control-file)" }))
exit $proc.ExitCode
