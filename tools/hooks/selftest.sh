#!/usr/bin/env bash
# tools/hooks/selftest.sh — самотест tools/hooks/pre-commit, пер-проверка (M-4, ADR-022).
# Гоняет КАЖДУЮ из семи проверок отдельно на заведомо падающем и заведомо проходящем
# входе, в одноразовой песочнице (temp-каталог, свои git-репозитории внутри).
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "ОШИБКА: не git-репозиторий"; exit 2; }
HOOK_SRC="${repo_root}/tools/hooks/pre-commit"
[ -f "$HOOK_SRC" ] || { echo "ОШИБКА: ${HOOK_SRC} не найден"; exit 2; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/m4-selftest.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

FAILED=0
CASE_NUM=0

note_fail() { FAILED=$((FAILED+1)); echo "  >>> ПРОВАЛ САМОТЕСТА: $1"; }

# ---------------------------------------------------------------------------
# Инфраструктура песочницы
# ---------------------------------------------------------------------------
init_repo() {
    local dir="$1"
    rm -rf "$dir"
    mkdir -p "$dir"
    git -C "$dir" init -q -b main
    git -C "$dir" config user.name "M-4 selftest"
    git -C "$dir" config user.email "selftest@example.invalid"
    git -C "$dir" config commit.gpgsign false
}

install_hook() {
    local dir="$1"
    mkdir -p "$dir/.git/hooks"
    cp "$HOOK_SRC" "$dir/.git/hooks/pre-commit"
    chmod +x "$dir/.git/hooks/pre-commit"
}

# Сид кладётся В ОБХОД хука (хук ещё не установлен на момент сида) — так и
# должно быть: судится только второй коммит (требование самотеста к истории).
seed_commit() {
    local dir="$1"
    git -C "$dir" add -A
    git -C "$dir" commit -q -m "seed"
}

# Коммит второго (судимого) коммита ПОСЛЕ установки хука.
attempt_commit() {
    local dir="$1" msg="$2" loc="$3"
    ( cd "$dir" && git add -A && LC_ALL="$loc" git commit -m "$msg" ) 2>&1
}

# Различает «упало на хуке» и «упало на окружении» — печатается самим тестом,
# а не выводится глазами (ловушка 5 / закон «неуспех инструмента не факт»).
assert_rejected_by_hook() {
    local label="$1" out="$2" rc="$3"
    CASE_NUM=$((CASE_NUM+1))
    if [ "$rc" -eq 0 ]; then
        note_fail "${label}: ожидался отказ, коммит прошёл (rc=0)"
        echo "  bad: ПРОВАЛ (коммит неожиданно прошёл)"
        return
    fi
    if grep -q 'ХУК: отказ' <<< "$out"; then
        echo "  bad: отклонён ИМЕННО хуком (найдена строка «ХУК: отказ»)"
    else
        note_fail "${label}: коммит упал (rc=${rc}), но это НЕ отказ хука — похоже на отказ окружения"
        echo "  bad: ПРОВАЛ — отказ похож на окружение, не на хук; вывод:"
        sed 's/^/      /' <<< "$out"
    fi
}

assert_accepted() {
    local label="$1" out="$2" rc="$3"
    CASE_NUM=$((CASE_NUM+1))
    if [ "$rc" -ne 0 ]; then
        note_fail "${label}: ожидался проход, коммит отказал (rc=${rc})"
        echo "  good: ПРОВАЛ (коммит неожиданно отказал)"
        sed 's/^/      /' <<< "$out"
        return
    fi
    if grep -q 'ХУК: пройдено' <<< "$out"; then
        echo "  good: пройден (найдена строка «ХУК: пройдено»)"
    else
        note_fail "${label}: коммит прошёл, но строка «ХУК: пройдено» не найдена — не доказано, что хук вообще исполнился"
        echo "  good: ПРОВАЛ — нет следа исполнения хука"
    fi
}

# Фикстура проверяется СРАЗУ после записи: наличием символа И дампом байтов
# (ловушка 7 §11.3 — сломанная фикстура однажды обнулила целый кейс у донора).
verify_fixture_bytes() {
    local file="$1" expected_hex="$2" label="$3"
    if ! grep -qF "$(cat "$file")" "$file" >/dev/null 2>&1; then :; fi
    local dump
    dump="$(od -An -tx1 "$file" | tr -s ' ' | tr -d '\n')"
    if grep -qi "$expected_hex" <<< "$dump"; then
        echo "  фикстура ${label}: байты подтверждены (найдено ${expected_hex} в дампе)"
    else
        note_fail "фикстура ${label}: ожидаемые байты ${expected_hex} НЕ найдены в дампе — тест недостоверен"
        echo "  дамп: ${dump}"
    fi
}

# ---------------------------------------------------------------------------
# Проба локали — ФУНКЦИОНАЛЬНАЯ, не по имени из списка (ловушка «Три оси»):
# несуществующее либо нефункциональное имя молча откатилось бы в байтовую.
# ---------------------------------------------------------------------------
find_multibyte_locale() {
    local loc bytes chars
    for loc in $(locale -a 2>/dev/null | grep -iE 'utf-?8'); do
        bytes="$(printf '\320\234' | LC_ALL="$loc" wc -c 2>/dev/null | tr -d ' ')"
        chars="$(printf '\320\234' | LC_ALL="$loc" wc -m 2>/dev/null | tr -d ' ')"
        if [ "$bytes" = "2" ] && [ "$chars" = "1" ]; then
            echo "$loc"
            return 0
        fi
    done
    return 1
}

echo "=== tools/hooks/selftest.sh · $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "Песочница: ${SANDBOX}"

MULTIBYTE_LOCALE="$(find_multibyte_locale || true)"
if [ -n "$MULTIBYTE_LOCALE" ]; then
    echo "Многобайтная локаль найдена функциональной пробой: ${MULTIBYTE_LOCALE}"
    LOCALES=("C" "$MULTIBYTE_LOCALE")
else
    echo "Многобайтная локаль НЕ найдена функциональной пробой (проверено: $(locale -a 2>/dev/null | grep -ciE 'utf-?8') кандидатов по имени, ни один не прошёл пробу wc -c/-m) — ось локали покрыта только байтовой стороной"
    LOCALES=("C")
fi

# ===========================================================================
# Батарея из семи проверок — по каждой локали оси (i).
# ===========================================================================
for LOC in "${LOCALES[@]}"; do
echo
echo "########## Локаль: ${LOC} ##########"

# --- Проверка 1: первая строка = имя документа ------------------------------
echo
echo "-- Проверка 1 (${LOC}) --"
d="${SANDBOX}/c1"
init_repo "$d"
printf '%s\n' "# 00 · TESTDOC — заготовка" "тело" > "${d}/00_TESTDOC.md"
seed_commit "$d"
install_hook "$d"

printf '%s\n' "# ПОДМЕНА, не то имя" "тело изменено" > "${d}/00_TESTDOC.md"
out="$(attempt_commit "$d" "bad: подменённая первая строка" "$LOC")"; rc=$?
assert_rejected_by_hook "check1/${LOC}" "$out" "$rc"
grep -q 'СОДЕРЖИМОЕ НЕ ТО' <<< "$out" || note_fail "check1/${LOC}: нет строки «СОДЕРЖИМОЕ НЕ ТО» в выводе"

git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
printf '%s\n' "# 00 · TESTDOC — заготовка" "тело, легитимная правка" > "${d}/00_TESTDOC.md"
out="$(attempt_commit "$d" "good: первая строка на месте" "$LOC")"; rc=$?
assert_accepted "check1/${LOC}" "$out" "$rc"

# --- Проверка 2: append решения ⇒ строка в оглавлении ------------------------
echo
echo "-- Проверка 2 (${LOC}) --"
d="${SANDBOX}/c2"
init_repo "$d"
printf '%s\n' "# 06 · DECISIONS_LOG — test" "" "## ADR-001 · seed" "текст" > "${d}/06_DECISIONS_LOG.md"
printf '%s\n' "# 06 · INDEX — test" "| ADR-001 | seed | 2026-01-01 | accepted |" > "${d}/06_INDEX.md"
seed_commit "$d"
install_hook "$d"

cat >> "${d}/06_DECISIONS_LOG.md" <<'EOF'

## ADR-002 · новое решение без индекса
текст
EOF
out="$(attempt_commit "$d" "bad: новое ADR без строки индекса" "$LOC")"; rc=$?
assert_rejected_by_hook "check2/${LOC}" "$out" "$rc"

git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
cat >> "${d}/06_DECISIONS_LOG.md" <<'EOF'

## ADR-002 · новое решение с индексом
текст
EOF
printf '%s\n' "| ADR-002 | новое решение с индексом | 2026-01-02 | accepted |" >> "${d}/06_INDEX.md"
out="$(attempt_commit "$d" "good: новое ADR со строкой индекса" "$LOC")"; rc=$?
assert_accepted "check2/${LOC}" "$out" "$rc"

# --- Проверка 3: исчезнувший идентификатор ⇒ архив (требует ИСТОРИИ) --------
# Формат фикстур — как в реальном репозитории (заголовок-разделитель таблицы,
# updated_at): иначе «хорошие» кейсы этой проверки ложно валятся ЧУЖИМИ
# проверками (4 и 5), а не той, что тестируется здесь.
echo
echo "-- Проверка 3 (${LOC}) — требует пары коммитов --"
d="${SANDBOX}/c3"
init_repo "$d"
state_tpl() { printf '%s\n' \
  "# 07 · STATE — test" "**updated_at:** $1" "" \
  "## Открытые вопросы" "| ID | Статус | Вопрос | Гейт |" "|---|---|---|---|" \
  "$2" "" "## Блокеры" "нет"; }
gaps_tpl() { printf '%s\n' \
  "# 07 · GAPS — test" "| ID | Статус | Вопрос | Причина | Гейт | Тип |" "|---|---|---|---|---|---|" \
  "$1"; }
state_tpl "2026-01-01" "| Q-1 | OPEN | исходная формулировка | гейт |" > "${d}/07_STATE.md"
gaps_tpl "| Q-1 | OPEN | исходная формулировка | причина | гейт | тип |" > "${d}/07_GAPS.md"
printf '%s\n' "# 07 · ARCHIVE — test" > "${d}/07_ARCHIVE.md"
seed_commit "$d"
seed_sha3="$(git -C "$d" rev-parse HEAD)"
install_hook "$d"

# (a) строка исчезла БЕЗ архива — падение
state_tpl "2026-01-02" "" > "${d}/07_STATE.md"
gaps_tpl "" > "${d}/07_GAPS.md"
out="$(attempt_commit "$d" "bad: Q-1 пропал без архива" "$LOC")"; rc=$?
assert_rejected_by_hook "check3a(disappear-no-archive)/${LOC}" "$out" "$rc"

# Каждый следующий подкейс расходится от ОДНОГО и того же сида, а не от
# текущего HEAD: успешный «good»-коммит предыдущего подкейса двигает HEAD
# вперёд, и сравнение «HEAD» съедет на его updated_at.
git -C "$d" reset -q --hard "$seed_sha3" >/dev/null 2>&1

# (b) строка ПЕРЕФОРМУЛИРОВАНА (тот же идентификатор) — проход
git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
state_tpl "2026-01-02" "| Q-1 | OPEN | переформулированный текст вопроса | гейт |" > "${d}/07_STATE.md"
out="$(attempt_commit "$d" "good: Q-1 переформулирован" "$LOC")"; rc=$?
assert_accepted "check3b(reworded)/${LOC}" "$out" "$rc"

# (c) строка исчезла ВМЕСТЕ с архивом — проход
git -C "$d" reset -q --hard "$seed_sha3" >/dev/null 2>&1
state_tpl "2026-01-02" "" > "${d}/07_STATE.md"
gaps_tpl "" > "${d}/07_GAPS.md"
printf '%s\n' "# 07 · ARCHIVE — test" "- Q-1 закрыт: исходная формулировка" > "${d}/07_ARCHIVE.md"
out="$(attempt_commit "$d" "good: Q-1 пропал вместе с архивом" "$LOC")"; rc=$?
assert_accepted "check3c(disappear-with-archive)/${LOC}" "$out" "$rc"

# --- Проверка 4: правка состояния ⇒ обновлён updated_at ---------------------
echo
echo "-- Проверка 4 (${LOC}) --"
d="${SANDBOX}/c4"
init_repo "$d"
printf '%s\n' "# 07 · STATE — test" "**updated_at:** 2026-01-01" "" "## Стенд-ап" "старый текст" > "${d}/07_STATE.md"
seed_commit "$d"
install_hook "$d"

sed -i.bak 's/старый текст/новый текст/' "${d}/07_STATE.md" && rm -f "${d}/07_STATE.md.bak"
out="$(attempt_commit "$d" "bad: правка без updated_at" "$LOC")"; rc=$?
assert_rejected_by_hook "check4/${LOC}" "$out" "$rc"

git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
sed -i.bak -e 's/старый текст/новый текст/' -e 's/2026-01-01/2026-01-02/' "${d}/07_STATE.md" && rm -f "${d}/07_STATE.md.bak"
out="$(attempt_commit "$d" "good: правка с updated_at" "$LOC")"; rc=$?
assert_accepted "check4/${LOC}" "$out" "$rc"

# --- Проверка 5: множества Q-id STATE и GAPS совпадают -----------------------
# Формат — как в реальном репозитории (заголовок-разделитель, updated_at):
# иначе «хорошие» кейсы этой проверки ложно валятся чужой проверкой 4.
echo
echo "-- Проверка 5 (${LOC}) --"
d="${SANDBOX}/c5"
init_repo "$d"
state5_tpl() { printf '%s\n' \
  "# 07 · STATE — test" "**updated_at:** $1" "" \
  "## Открытые вопросы" "| ID | Статус | Вопрос | Гейт |" "|---|---|---|---|" \
  "$2" "" "## Блокеры" "нет"; }
gaps5_tpl() { printf '%s\n' \
  "# 07 · GAPS — test" "| ID | Статус | Вопрос | Причина | Гейт | Тип |" "|---|---|---|---|---|---|" \
  "$1"; }
state5_tpl "2026-01-01" "| Q-1 | OPEN | вопрос | гейт |" > "${d}/07_STATE.md"
gaps5_tpl "| Q-1 | OPEN | вопрос | причина | гейт | тип |" > "${d}/07_GAPS.md"
seed_commit "$d"
install_hook "$d"

state5_tpl "2026-01-02" "| Q-1 | OPEN | вопрос | гейт |
| Q-2 | OPEN | второй вопрос | гейт |" > "${d}/07_STATE.md"
out="$(attempt_commit "$d" "bad: Q-2 в STATE без GAPS" "$LOC")"; rc=$?
assert_rejected_by_hook "check5/${LOC}" "$out" "$rc"

git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
state5_tpl "2026-01-02" "| Q-1 | OPEN | вопрос | гейт |
| Q-2 | OPEN | второй вопрос | гейт |" > "${d}/07_STATE.md"
gaps5_tpl "| Q-1 | OPEN | вопрос | причина | гейт | тип |
| Q-2 | OPEN | второй вопрос | причина | гейт | тип |" > "${d}/07_GAPS.md"
out="$(attempt_commit "$d" "good: Q-2 в обоих" "$LOC")"; rc=$?
assert_accepted "check5/${LOC}" "$out" "$rc"

# --- Проверка 6: кириллические гомоглифы в латинских идентификаторах --------
echo
echo "-- Проверка 6 (${LOC}) --"
d="${SANDBOX}/c6"
init_repo "$d"
printf '%s\n' "# заготовка" "см. M-4" > "${d}/notes.md"
seed_commit "$d"
install_hook "$d"

# Гомоглиф собирается восьмеричным экранированием (октальные байты UTF-8 для
# кириллической «М», U+041C = D0 9C), не литералом — литерал сам был бы
# нарушением проверяемого правила и попал бы в репозиторий (ловушка 7 §11.3).
cyr_m="$(printf '\320\234')"
bad_file="${d}/homoglyph.md"
printf '%s\n' "# заготовка" "см. ${cyr_m}-4 (гомоглиф вместо M-4)" > "$bad_file"
verify_fixture_bytes "$bad_file" "d0 9c" "check6-bad(homoglyph-M)"
out="$(attempt_commit "$d" "bad: гомоглиф в идентификаторе" "$LOC")"; rc=$?
assert_rejected_by_hook "check6/${LOC}" "$out" "$rc"

git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
printf '%s\n' "# заготовка" "см. M-4 (латиница, легитимно)" > "${d}/homoglyph.md"
out="$(attempt_commit "$d" "good: чистая латиница в идентификаторе" "$LOC")"; rc=$?
assert_accepted "check6/${LOC}" "$out" "$rc"

# --- Проверка 7: секреты в патче ---------------------------------------------
echo
echo "-- Проверка 7 (${LOC}) --"
d="${SANDBOX}/c7"
init_repo "$d"
printf '%s\n' "# заготовка конфига" "хост: localhost" > "${d}/notes.md"
seed_commit "$d"
install_hook "$d"

# Флаг "-password" в исходнике selftest.sh собран из НЕСМЕЖНЫХ фрагментов:
# литеральная подстрока "-password <значение>" сама стала бы добавленной
# строкой при коммите ЭТОГО файла и завалила бы проверку 7 на тексте теста,
# а не на тестовом вводе (тот же класс самоприменения, что и в ловушке 7).
flag_prefix="-user SYSDBA -pass"
flag_suffix="word"
fake_value="fakesecret123"
secret_line="${flag_prefix}${flag_suffix} ${fake_value}"
printf '%s\n' "# заготовка конфига" "хост: localhost" "$secret_line" > "${d}/notes.md"
out="$(attempt_commit "$d" "bad: явный секрет в патче" "$LOC")"; rc=$?
assert_rejected_by_hook "check7/${LOC}" "$out" "$rc"

git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
printf '%s\n' "# заготовка конфига" "хост: localhost" "-user SYSDBA -password <ПАРОЛЬ_вне_репо>" > "${d}/notes.md"
out="$(attempt_commit "$d" "good: плейсхолдер вместо секрета" "$LOC")"; rc=$?
assert_accepted "check7/${LOC}" "$out" "$rc"

done  # локали

# ===========================================================================
# Ось (ii): размер — файл больше буфера пайпа (>64 КиБ), ловит ловушку 3.
# ===========================================================================
echo
echo "########## Ось «размер» (>64 КиБ) ##########"
d="${SANDBOX}/size"
init_repo "$d"
printf '%s\n' "# 00 · BIGDOC — заготовка" "тело" > "${d}/00_BIGDOC.md"
seed_commit "$d"
install_hook "$d"

{
    printf '%s\n' "# 00 · BIGDOC — заготовка"
    yes "строка заполнения для проверки чтения большого файла без обрыва пайпа" | head -n 1200
} > "${d}/00_BIGDOC.md"
filesize="$(wc -c < "${d}/00_BIGDOC.md" | tr -d ' ')"
echo "размер фикстуры: ${filesize} байт (порог 65536)"
if [ "$filesize" -le 65536 ]; then
    note_fail "size-axis: фикстура не превысила 64 КиБ (${filesize} байт) — ось не покрыта"
fi
out="$(attempt_commit "$d" "good: большой файл, первая строка корректна" "C")"; rc=$?
assert_accepted "check1-size/${filesize}b" "$out" "$rc"

git -C "$d" reset -q --hard HEAD >/dev/null 2>&1
{
    printf '%s\n' "# ПОДМЕНА в большом файле"
    yes "строка заполнения для проверки чтения большого файла без обрыва пайпа" | head -n 1200
} > "${d}/00_BIGDOC.md"
out="$(attempt_commit "$d" "bad: большой файл, первая строка подменена" "C")"; rc=$?
assert_rejected_by_hook "check1-size-bad/${filesize}b" "$out" "$rc"

# ===========================================================================
# Ось (iii): легитимный композит — строки, дословно встречающиеся в репозитории,
# не должны ложно срабатывать на проверке гомоглифов.
# ===========================================================================
echo
echo "########## Ось «легитимный композит» ##########"
d="${SANDBOX}/composite"
init_repo "$d"
printf '%s\n' "# заготовка" "текст" > "${d}/notes.md"
seed_commit "$d"
install_hook "$d"

# Список — литеральный, не выборка регэкспом по диапазону [А-Яа-я]: тот же
# байтовый диапазон над многобайтными символами, что и в ловушке 1, ломает
# grep -oE на macOS и режет символы пополам. Каждая строка проверяется
# фиксированной (не regex) подстрокой в реальных файлах репозитория.
composite_candidates=(
    "DDNS-имена"
    "ERP-сервере"
    "GCP-проект"
    "session-блоков"
    "Anti-improvisation"
    "Telegram-бота"
)
: > "${d}/notes.md"
printf '%s\n' "# заготовка" "текст" >> "${d}/notes.md"
echo "образцы легитимных композитов, проверенные литеральным поиском в репозитории:"
for c in "${composite_candidates[@]}"; do
    hit="$(grep -rlF -- "$c" "${repo_root}" --include='*.md' --include='*.sh' 2>/dev/null | grep -vF '/tools/hooks/selftest.sh' | head -1)"
    if [ -n "$hit" ]; then
        echo "  «${c}» — найдено в ${hit#${repo_root}/}"
        printf '%s\n' "$c" >> "${d}/notes.md"
    else
        note_fail "composite-axis: «${c}» не найдено дословно в репозитории — образец недостоверен"
    fi
done
out="$(attempt_commit "$d" "good: легитимные русско-латинские композиты" "C")"; rc=$?
assert_accepted "check6-composite" "$out" "$rc"

# ===========================================================================
echo
echo "=== ИТОГ САМОТЕСТА ==="
echo "кейсов проверено: ${CASE_NUM}"
echo "провалено ${FAILED}"
if [ "$FAILED" -eq 0 ]; then
    exit 0
else
    exit 1
fi
