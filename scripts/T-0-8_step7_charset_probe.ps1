# T-0-8_step7_charset_probe.ps1 — CONTEXT GAP `LOMBARD_DB_CHARSET`, КЛАСС B, сервер ERP.
#
# Область: НАЙТИ (способ 1) или ИЗМЕРИТЬ (способ 2) кодировку подключения Firebird
# к D:\PawnShop_DOL\DB\DOL.FDB. Ничего не устанавливает, не создаёт и не меняет —
# только чтение файлов сервера и read-only подключение к базе через уже проверенную
# точку доступа `connector/agent/access_point.py`. Значение НЕ угадывается: скрипт
# либо печатает найденное в конфиге приложения PawnShop, либо печатает результат
# пробных подключений для визуальной проверки человеком (05 §I: предикат читаемости
# кириллицы определяется человеком, не автоматикой).
#
# Способ 1 исполняется первым. Даёт ответ — способ 2 не нужен, это фиксируется в
# артефакте явной строкой. Не даёт — переходим к способу 2 (см. подсказку в конце
# вывода этого скрипта: она называет команду запуска Python-пробы).
#
# НЕ исполнять без отдельного подтверждения Ilyas по карточке.

$ErrorActionPreference = 'Continue'   # поиск файлов не должен падать целиком на одном ACL-отказе

'##### T-0-8 / шаг 7, способ 1 — поиск конфигурации PawnShop с кодировкой подключения #####'
'ЛОКАЛЬНОЕ ВРЕМЯ ЗАПУСКА : ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss K')
''

# Строка базы, по которой ищем — она уже опубликована 11_INFRA_FACTS.md и
# briefs/T-0-8.md §«Входы», это не новый секрет.
$needle = 'DOL.FDB'

# Стандартные места установки Windows-приложений плюс каталог самой базы
# (конфиг клиентского ПО нередко лежит рядом с данными, а не в Program Files).
$roots = @(
    'C:\Program Files',
    'C:\Program Files (x86)',
    'C:\ProgramData',
    'D:\PawnShop_DOL',
    'C:\PawnShop_DOL'
) | Where-Object { Test-Path $_ }

'КОРНИ ПОИСКА (существующие) : ' + ($roots -join '; ')
''

'===== ПОИСК ФАЙЛОВ, СОДЕРЖАЩИХ "' + $needle + '" ====='
$hits = foreach ($root in $roots) {
    Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -match '^\.(ini|cfg|conf|config|xml|txt|json|reg|inf)$' -or $_.Extension -eq '' } |
        ForEach-Object {
            try {
                $m = Select-String -Path $_.FullName -Pattern ([regex]::Escape($needle)) -ErrorAction Stop
                if ($m) { $_.FullName }
            } catch { }
        }
}
$hits = $hits | Sort-Object -Unique

if (-not $hits) {
    'НЕ НАЙДЕНО ни одного файла с "' + $needle + '" в перечисленных корнях.'
    'СПОСОБ 1 НЕ ДАЛ ОТВЕТА — переходить к способу 2 (см. карточку, T-0-8_step7_charset_probe.py).'
} else {
    'НАЙДЕНО файлов : ' + $hits.Count
    foreach ($f in $hits) { '  - ' + $f }
    ''
    '===== СТРОКИ С КЛЮЧЕВЫМ СЛОВОМ "CHARSET" В НАЙДЕННЫХ ФАЙЛАХ ====='
    $charsetHits = 0
    foreach ($f in $hits) {
        try {
            $cs = Select-String -Path $f -Pattern 'charset|character[_ ]set|lc_ctype|codepage|кодировк' -ErrorAction Stop
        } catch { $cs = $null }
        if ($cs) {
            $charsetHits++
            'ФАЙЛ : ' + $f
            $cs | ForEach-Object { '  строка ' + $_.LineNumber + ': ' + $_.Line.Trim() }
        }
    }
    if ($charsetHits -eq 0) {
        'В найденных файлах строк с "charset"/"character set"/"lc_ctype"/"codepage" НЕТ.'
        'СПОСОБ 1 НАШЁЛ КОНФИГ, НО НЕ КОДИРОВКУ — переходить к способу 2.'
    } else {
        'СПОСОБ 1 ДАЛ КАНДИДАТ(Ы) ВЫШЕ. Сверить со списком кандидатов способа 2 '
        '(WIN1251, UTF8, NONE, DOS866) и подтвердить визуально способом 2 ПЕРЕД записью в '
        'run_daily_wrapper.ps1 — конфиг приложения может описывать не тот же параметр '
        '(например, локальную кодовую страницу консоли клиента, а не charset подключения к БД).'
    }
}
''
'===== ПОДСКАЗКА НА СЛУЧАЙ, ЕСЛИ СПОСОБ 1 НЕ ДАЛ ОТВЕТА ====='
'Скопировать connector/agent/charset_probe.py тем же способом, что и код агента '
'(шаг 6 — RDP/notepad или архив), в C:\LombardAgent\code\connector\agent\ РЯДОМ с уже '
'установленным кодом (agent.py, access_point.py, schema_guard.py уже там). Запустить:'
'  cd C:\LombardAgent\code'
'  python connector\agent\charset_probe.py'
'Пароль LOMBARD_RO скрипт запросит интерактивно (ввод скрыт, никуда не пишется и не печатается).'
