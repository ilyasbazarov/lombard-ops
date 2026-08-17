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
    Write-Error 'CONTEXT GAP: LOMBARD_DB_CHARSET ne zadan - proby ne zapuskayutsya bez parametra podklyucheniya k Firebird.'
    exit 2
}
$logDir = "C:\LombardAgent\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutFile = Join-Path $logDir ("negative_probes_{0}.out.log" -f $stamp)
$stderrFile = Join-Path $logDir ("negative_probes_{0}.err.log" -f $stamp)
$proc = Start-Process -FilePath "C:\Program Files\Python314\python.exe" -ArgumentList '"C:\LombardAgent\code\scripts\T-0-8_step7_negative_probes.py"' -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
Add-Content -Path $stdoutFile -Value ("EXITCODE: {0}" -f $proc.ExitCode)
Add-Content -Path $stdoutFile -Value ("WHOAMI: {0}" -f [System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
exit $proc.ExitCode
