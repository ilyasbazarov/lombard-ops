#!/usr/bin/env bash
# scripts/T-0-6_step3_prepare_delivery.sh — T-0-6, шаг 3 (класс A, ЛОКАЛЬНО)
#
# Готовит base64-payload и точные команды `certutil -decode` / `Get-FileHash`
# для доставки ДВУХ файлов шага 3 брифа T-0-6 на сервер ERP:
#   - connector/agent/discovery_t0_6.py
#   - scripts/T-0-6_run_discovery.ps1
# (test_discovery_t0_6.py на сервер не едет — оффлайн-тест, выполняется
# локально без подключения к базе, см. брифа T-0-6 шаг 2 и прецедент T-0-4a.)
#
# Паттерн — scripts/T-0-4a_step3_prepare_delivery.sh, применённый реально
# в T-0-4a шаг 3.
#
# Что этот скрипт НЕ делает (класс A): не открывает RDP, не пишет ничего на
# сервер, не запускает ничего удалённо. Читает ДВА файла репозитория на этой
# машине и пишет производные (.b64, .sha256, .decode_cmd.txt) в локальный
# каталог — вставка на сервере и запуск certutil/сверка хеша есть действие
# по RDP, класс B, со своей карточкой подтверждения.
#
# Выходной каталог не коммитится — регенерируемый артефакт.
#
# Запуск: bash scripts/T-0-6_step3_prepare_delivery.sh [каталог_вывода]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-${REPO_ROOT}/reference/_local_delivery_t0_6_step3}"

mkdir -p "$OUT_DIR"

FILE_1_REL="connector/agent/discovery_t0_6.py"
FILE_1_DEST='C:\LombardAgent\code\connector\agent\discovery_t0_6.py'
FILE_1_OUT="discovery_t0_6.py"

FILE_2_REL="scripts/T-0-6_run_discovery.ps1"
FILE_2_DEST='C:\LombardAgent\code\scripts\T-0-6_run_discovery.ps1'
FILE_2_OUT="T-0-6_run_discovery.ps1"

prepare_one() {
    local out_name="$1" src_rel="$2" dest_win="$3"
    local src="${REPO_ROOT}/${src_rel}"

    if [[ ! -f "$src" ]]; then
        echo "CONTEXT GAP: исходный файл не найден в репозитории: ${src}" >&2
        exit 2
    fi

    local b64_file="${OUT_DIR}/${out_name}.b64"
    local sha_file="${OUT_DIR}/${out_name}.sha256"
    local cmd_file="${OUT_DIR}/${out_name}.decode_cmd.txt"

    base64 -i "$src" > "$b64_file"
    shasum -a 256 "$src" | awk '{print $1}' > "$sha_file"

    {
        echo "# Файл источника: ${src_rel} (репозиторий, коммит $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?'))"
        echo "# Назначение на сервере: ${dest_win}"
        echo "#"
        echo "# Порядок на сервере (PowerShell), ПОСЛЕ того как текст ${out_name}.b64"
        echo "# вставлен в C:\\Temp\\${out_name}.b64 (Notepad, ASCII-содержимое base64 безопасно):"
        echo "#"
        echo "# certutil -decode НЕ перезаписывает существующий файл назначения (найдено"
        echo "# реальным прогоном 2026-08-18 в T-0-4a). Если файл на сервере уже"
        echo "# существует (повторная доставка правленой версии), Remove-Item ОБЯЗАТЕЛЕН"
        echo "# перед certutil -decode; при первой доставке файла не существует, и"
        echo "# Remove-Item с -ErrorAction SilentlyContinue безопасен в обоих случаях."
        echo "Remove-Item \"${dest_win}\" -ErrorAction SilentlyContinue"
        echo "certutil -decode C:\\Temp\\${out_name}.b64 \"${dest_win}\""
        echo "(Get-FileHash \"${dest_win}\" -Algorithm SHA256).Hash.ToLower()"
        echo "# ожидаемое значение (сверить построчно с выводом команды выше):"
        cat "$sha_file"
    } > "$cmd_file"

    echo "готово: ${out_name}"
    echo "  payload:  ${b64_file} ($(wc -c < "$b64_file" | tr -d ' ') байт base64)"
    echo "  команды:  ${cmd_file}"
    echo "  ожидаемый SHA-256 оригинала: $(cat "$sha_file")"
}

prepare_one "$FILE_1_OUT" "$FILE_1_REL" "$FILE_1_DEST"
echo
prepare_one "$FILE_2_OUT" "$FILE_2_REL" "$FILE_2_DEST"

cat <<EOF

Итог: файлы лежат в ${OUT_DIR} (каталог не коммитится, регенерируется этим
скриптом при необходимости).

Дальше — ваше действие по RDP на сервере ERP (класс B, отдельная карточка,
не выполняется этим скриптом и не выполняется этой сессией):
  1. открыть <имя>.b64 локально -> скопировать текст целиком;
  2. на сервере: notepad C:\\Temp\\<имя>.b64 -> вставить -> сохранить;
  3. выполнить команды из соответствующего <имя>.decode_cmd.txt;
  4. сверить напечатанный Get-FileHash со значением, напечатанным этим
     скриптом (оба в нижнем регистре, посимвольно) — расхождение хоть в
     одном символе означает повреждение при передаче, файл на сервере не
     используется, доставка повторяется.
EOF
