# T-0-8_step5b_server_setup.ps1 — шаг 5-Б брифа (ПОПРАВКА 3, ADR-050), КЛАСС B, сервер ERP.
#
# Область ЭТОГО скрипта (только то, что не зависит от issuer-uri и от провайдера федерации,
# см. CONTEXT GAP в сессии — issuer-uri ещё не назван):
#   1) установка Python (последняя стабильная 3.x)
#   2) генерация пары RSA 2048 НА ДИСКЕ (не в памяти)
#   3) экспорт JWKS (RFC 7517: kty, alg, use, kid, n, e) в отдельный файл
#   4) ограничение прав на файл приватного ключа — ТОЛЬКО учётная запись службы агента (icacls)
#   5) включение и проверка службы времени Windows (w32tm)
#
# НЕ входит: генерация файла конфигурации учётных данных (`create-cred-config`) — она требует
# провайдера федерации, а тот требует issuer-uri (CONTEXT GAP, шаг 5-А п.4, не в этом скрипте).
#
# НЕ исполнять без отдельного подтверждения Ilyas по карточке. Печатает найденное/сделанное,
# не молчит (стиль probe_wif_identity.ps1). Приватный ключ НИКОГДА не печатается — ни целиком,
# ни фрагментом; в лог идёт только путь, права, kid, длина модуля и SHA-256 отпечаток открытой
# части.
#
# Параметр ServiceAccountName ОБЯЗАТЕЛЕН и НЕ имеет значения по умолчанию: имя учётной записи
# службы агента этим брифом не названо (сервер — рабочая группа, не домен, служба заводится
# шагом 6). Ilyas подтверждает/передаёт её вместе с картой подтверждения этого шага.
#
# Запуск:
#   powershell -ExecutionPolicy Bypass -File T-0-8_step5b_server_setup.ps1 `
#       -ServiceAccountName ".\lombard-agent-svc"

param(
    [Parameter(Mandatory = $true)]
    [string]$ServiceAccountName,

    [string]$KeyDir = "C:\LombardAgent\keys",

    [string]$Kid = ("lombard-agent-" + (Get-Date -Format "yyyyMMdd")),

    [int]$KeySize = 2048
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

'##### T-0-8 / шаг 5-Б — установка Python, ключи, JWKS, служба времени #####'
'ЛОКАЛЬНОЕ ВРЕМЯ ЗАПУСКА : ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss K')
'СЛУЖЕБНАЯ УЧЁТКА (для icacls) : ' + $ServiceAccountName
'КАТАЛОГ КЛЮЧЕЙ : ' + $KeyDir
'KID : ' + $Kid
''

# ============================================================================
# 1. PYTHON — установка последней стабильной 3.x
# ============================================================================
'===== 1. PYTHON ====='
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    'Python уже присутствует: ' + (python --version 2>&1)
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        'winget найден — установка пакетом Python.Python.3.12 (Microsoft-каталог winget), тихий режим.'
        winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    } else {
        'winget НЕ найден — метод отступления: официальный MSI-инсталлятор с python.org.'
        'Требуется вручную указать точную ссылку релиза (последняя стабильная 3.x на дату установки,'
        'https://www.python.org/downloads/windows/) — этот скрипт её не подставляет: версия'
        'меняется быстрее, чем правится репозиторий, а угадывание номера патч-версии запрещено'
        '(anti-improvisation). ДЕЙСТВИЕ ПРЕРВАНО на этом пункте до явного ответа: winget или'
        'ручная ссылка на MSI.'
        exit 1
    }
    # PATH текущей сессии PowerShell не обновляется автоматически после установки —
    # перечитываем машинный + пользовательский PATH из реестра явно, вместо того чтобы
    # молча считать python отсутствующим.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        'PYTHON УСТАНОВЛЕН : ' + (python --version 2>&1) + ' (' + $pythonCmd.Source + ')'
    } else {
        'ПРОВЕРКА ПОСЛЕ УСТАНОВКИ НЕ НАШЛА python В PATH ТЕКУЩЕЙ СЕССИИ —'
        'перезапустить консоль (новый процесс подхватит обновлённый PATH) и повторить'
        '`python --version` вручную; это гэп наблюдения этой сессии, не факт отказа установки.'
        exit 1
    }
}
''

# ============================================================================
# 2-3. RSA 2048 НА ДИСКЕ + JWKS (через Python/cryptography — та же библиотека,
#      что читает ключ jwt_signer.py, совместимость гарантирована форматом PEM)
# ============================================================================
'===== 2-3. RSA 2048 НА ДИСКЕ + ЭКСПОРТ JWKS ====='
'Установка зависимости `cryptography` (та же библиотека, что использует connector/agent/jwt_signer.py):'
python -m pip install --quiet --upgrade pip
python -m pip install --quiet "cryptography>=41"
if ($LASTEXITCODE -ne 0) {
    'УСТАНОВКА cryptography УПАЛА — генерация ключа дальше не идёт.'
    exit 1
}
New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null

$privateKeyPath = Join-Path $KeyDir "private_key.pem"
$jwksPath = Join-Path $KeyDir "jwks.json"

$pyScript = @"
import base64, hashlib, json, sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

private_key = rsa.generate_private_key(public_exponent=65537, key_size=$KeySize)
pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
with open(r"$privateKeyPath", "wb") as f:
    f.write(pem)

pub = private_key.public_key()
numbers = pub.public_numbers()

def b64url(i: int, length: int) -> str:
    b = i.to_bytes(length, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

n_bytes = (numbers.n.bit_length() + 7) // 8
e_bytes = (numbers.e.bit_length() + 7) // 8
jwk = {
    "kty": "RSA",
    "alg": "RS256",
    "use": "sig",
    "kid": "$Kid",
    "n": b64url(numbers.n, n_bytes),
    "e": b64url(numbers.e, e_bytes),
}
with open(r"$jwksPath", "w", encoding="ascii") as f:
    json.dump({"keys": [jwk]}, f)

pub_der = pub.public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)
fingerprint = hashlib.sha256(pub_der).hexdigest()

print("KEY_SIZE_BITS=" + str(private_key.key_size))
print("MODULUS_BYTES=" + str(n_bytes))
print("SHA256_FINGERPRINT_PUBLIC=" + fingerprint)
"@

$pyScriptPath = Join-Path $env:TEMP "t0_8_genkey.py"
[System.IO.File]::WriteAllText($pyScriptPath, $pyScript, (New-Object System.Text.UTF8Encoding($false)))

$genOutput = & python $pyScriptPath 2>&1
if ($LASTEXITCODE -ne 0) {
    'ГЕНЕРАЦИЯ КЛЮЧА УПАЛА (текст ошибки дословно, приватный ключ в вывод не попадает):'
    $genOutput
    exit 1
}
'ПРИВАТНЫЙ КЛЮЧ : ' + $privateKeyPath + ' (содержимое НЕ печатается)'
'JWKS ФАЙЛ      : ' + $jwksPath + ' (открытая часть — не секрет, печатается ниже целиком)'
$genOutput
Remove-Item $pyScriptPath -Force
''
'СОДЕРЖИМОЕ JWKS (открытая часть, RFC 7517, не секрет):'
Get-Content $jwksPath
''

# ============================================================================
# 4. ПРАВА НА ФАЙЛ ПРИВАТНОГО КЛЮЧА — ТОЛЬКО учётная запись службы агента
# ============================================================================
'===== 4. ПРАВА НА ПРИВАТНЫЙ КЛЮЧ (icacls) ====='
icacls $privateKeyPath /inheritance:r
icacls $privateKeyPath /grant:r ("${ServiceAccountName}:(R)")
icacls $privateKeyPath /grant:r "SYSTEM:(F)"
'ПРАВА ПОСЛЕ ОГРАНИЧЕНИЯ (предъявляется выводом команды, не утверждением):'
icacls $privateKeyPath
''

# ============================================================================
# 5. СЛУЖБА ВРЕМЕНИ WINDOWS — включение и проверка (условие приёмки шага, ADR-050 п.9)
# ============================================================================
'===== 5. СЛУЖБА ВРЕМЕНИ WINDOWS (w32tm) ====='
$svc = Get-Service -Name W32Time -ErrorAction SilentlyContinue
if ($null -eq $svc) {
    'СЛУЖБА W32Time НЕ ЗАРЕГИСТРИРОВАНА — регистрация:'
    w32tm /register
    $svc = Get-Service -Name W32Time -ErrorAction SilentlyContinue
}
if ($svc.Status -ne 'Running') {
    'СЛУЖБА W32Time НЕ ЗАПУЩЕНА (' + $svc.Status + ') — запуск:'
    Set-Service -Name W32Time -StartupType Automatic
    Start-Service -Name W32Time
}
Start-Sleep -Seconds 2
'СТАТУС ПОСЛЕ ЗАПУСКА:'
Get-Service -Name W32Time | Format-Table Name, Status, StartType -AutoSize | Out-String
'ВЫВОД w32tm /query /status (обязан быть БЕЗ КОДА ОШИБКИ — условие приёмки шага):'
w32tm /query /status
if ($LASTEXITCODE -ne 0) {
    'w32tm /query /status ВЕРНУЛ КОД ' + $LASTEXITCODE + ' — приёмка шага НЕ закрыта, это отказ,'
    'а не гэп наблюдения: код и текст выше напечатаны дословно.'
    exit 1
}
''
'##### ГОТОВО. Ниже — что предъявить в артефакте reference/T-0-8_federation_setup_<дата>.md #####'
'- путь к приватному ключу и вывод icacls (права)'
'- kid, длину модуля (байт), SHA-256 отпечаток открытой части (из вывода раздела 2-3)'
'- содержимое JWKS целиком (не секрет)'
'- версию Python'
'- вывод w32tm /query /status без ошибки'
'ПРИВАТНЫЙ КЛЮЧ ЦЕЛИКОМ ИЛИ ЧАСТЬЮ В АРТЕФАКТ НЕ ИДЁТ НИКОГДА.'
