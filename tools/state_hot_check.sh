#!/usr/bin/env bash
# tools/state_hot_check.sh — гейт горячего состояния (M-7, ADR-085).
#
# Меряет ДВЕ вещи и обе печатает числом плюс совпавшими строками:
#   (1) секция «Подробности для модели» 07_STATE.md — пункты без якоря, пункты с
#       закрытыми якорями, пункты с неразрешимым якорем;
#   (2) цену обязательного контекста в байтах против назначенного порога.
#
# Слой ПРЕДУПРЕДИТЕЛЬНЫЙ (ADR-085 п.5, норма ADR-074 п.7): пункт снимается ТЕМ ЖЕ
# коммитом, которым закрывается его якорь, поэтому в момент проверки признак
# неизбежно срабатывает на законном содержании и блокировать не имеет права.
# Код возврата 0 всегда, кроме отказа среды и провала самотеста.
#
# Якорь открыт, если:
#   T-…/M-… — строка есть в таблице 04_ROADMAP.md и её статус не содержит «done»;
#   Q-…     — строка есть в таблице 07_GAPS.md (закрытый вопрос из неё уезжает).
set -u

STATE_FILE="${STATE_FILE:-07_STATE.md}"
ROADMAP_FILE="${ROADMAP_FILE:-04_ROADMAP.md}"
GAPS_FILE="${GAPS_FILE:-07_GAPS.md}"
CONTEXT_FILES="${CONTEXT_FILES:-00_CHARTER.md 05_CONVENTIONS.md 07_STATE.md CLAUDE.md}"
CONTEXT_LIMIT="${CONTEXT_LIMIT:-120000}"

run_check() {
    python3 - "$STATE_FILE" "$ROADMAP_FILE" "$GAPS_FILE" "$CONTEXT_LIMIT" $CONTEXT_FILES <<'PY'
# -*- coding: utf-8 -*-
import io, os, re, sys

state_p, roadmap_p, gaps_p = sys.argv[1], sys.argv[2], sys.argv[3]
limit = int(sys.argv[4])
context_files = sys.argv[5:]

def read(p):
    if not os.path.exists(p):
        print(u'ОТКАЗ СРЕДЫ: файл не найден — %s' % p)
        sys.exit(2)
    return io.open(p, encoding='utf-8').read().split('\n')

# --- какие строки роудмапа и реестра вопросов открыты ------------------------
open_tasks, closed_tasks = set(), set()
for line in read(roadmap_p):
    m = re.match(r'^\|\s*([TM]-[0-9][0-9A-Za-z-]*)\s*\|', line)
    if not m:
        continue
    cells = [c.strip() for c in line.split('|')]
    ident = m.group(1)
    status = cells[7] if len(cells) > 7 else ''
    (closed_tasks if 'done' in status.lower() else open_tasks).add(ident)

open_gaps = set()
for line in read(gaps_p):
    m = re.match(r'^\|\s*(Q-[0-9]+)\s*\|', line)
    if m:
        open_gaps.add(m.group(1))

# --- разбор секции -----------------------------------------------------------
lines = read(state_p)
start = None
for i, l in enumerate(lines):
    if l.startswith('## Подробности для модели'):
        start = i
        break
if start is None:
    print(u'ОТКАЗ СРЕДЫ: в %s нет секции «Подробности для модели»' % state_p)
    sys.exit(2)
end = len(lines)
for i in range(start + 1, len(lines)):
    if lines[i].startswith('## '):
        end = i
        break

items = []
cur = None
for n in range(start + 1, end):
    l = lines[n]
    if l.startswith('- '):
        if cur:
            items.append(cur)
        cur = [n + 1, l]
    elif cur is None:
        pass
if cur:
    items.append(cur)

no_anchor, cold, unresolved = [], [], []
for n, text in items:
    m = re.match(r'^- \*\*\[якорь:\s*([^\]]+)\]\*\*', text)
    if not m:
        no_anchor.append((n, text))
        continue
    ids = [x.strip() for x in m.group(1).split(',') if x.strip()]
    bad = [i for i in ids
           if i not in open_tasks and i not in closed_tasks and i not in open_gaps]
    if bad:
        unresolved.append((n, text, bad))
        continue
    if not any((i in open_tasks) or (i in open_gaps) for i in ids):
        cold.append((n, text))

def show(title, rows, extra=None):
    print(u'-- %s --' % title)
    print(u'count=%d' % len(rows))
    for row in rows:
        n, text = row[0], row[1]
        tail = u'' if extra is None else u'  [неразрешимо: %s]' % u', '.join(row[2])
        print(u'%s:%d: %s%s' % (state_p, n, text[:150], tail))
    print(u'')

print(u'=== state_hot_check.sh · секция «Подробности для модели» ===')
print(u'пунктов в секции: %d · открытых строк роудмапа: %d · открытых вопросов: %d'
      % (len(items), len(open_tasks), len(open_gaps)))
print(u'')
show(u'1. Пункты БЕЗ якоря (правило ADR-085: у пункта есть другой дом)', no_anchor)
show(u'2. Пункты, у которых ВСЕ якоря закрыты — снять в 07_ARCHIVE дословно', cold)
show(u'3. Пункты с якорем, не найденным ни в роудмапе, ни в реестре вопросов', unresolved, extra=True)

# --- 5. открытая строка карты без СВОЕЙ строки таблицы мандата (ADR-072, ADR-088)
mandate = set()
in_mandate = False
for l in lines:
    if l.startswith('## Задачи и мандат'):
        in_mandate = True
        continue
    if in_mandate and l.startswith('## '):
        break
    if in_mandate:
        m = re.match(r'^\|\s*([TM]-[0-9][0-9A-Za-z-]*)[\s|]', l)
        if m:
            mandate.add(m.group(1))
missing = sorted(i for i in open_tasks if i not in mandate)
print(u'-- 5. Открытые строки карты БЕЗ своей строки таблицы мандата (ADR-072) --')
print(u'count=%d' % len(missing))
for i in missing:
    print(u'%s: задача открыта в 04_ROADMAP, строки в «Задачи и мандат» нет — класс не назначен, '
          u'сборка брифа обязана остановиться' % i)
print(u'')

total = 0
print(u'-- 4. Цена обязательного контекста (байты) --')
for p in context_files:
    if not os.path.exists(p):
        print(u'%s: ФАЙЛ НЕ НАЙДЕН' % p)
        continue
    size = os.path.getsize(p)
    total += size
    print(u'%s: %d' % (p, size))
print(u'count=%d (порог %d)' % (total, limit))
if total > limit:
    print(u'ПОРОГ ПРЕВЫШЕН на %d байт — повод к вытеснению, не стоп-условие (ADR-085 п.6)' % (total - limit))
else:
    print(u'в пределах порога, запас %d байт' % (limit - total))
print(u'')
print(u'=== ИТОГ === без якоря: %d · остывших: %d · неразрешимых: %d · без мандата: %d · контекст: %d/%d'
      % (len(no_anchor), len(cold), len(unresolved), len(missing), total, limit))
PY
}

# ---------------------------------------------------------------------------
selftest() {
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    failed=0
    passed=0

    cat > "$tmp/road.md" <<'EOF'
| ID | Задача | §6 | Класс | Метка | Зависит от | Статус | Приёмка |
|---|---|---|---|---|---|---|---|
| T-9-1 | живая задача | 1 | A | продукт | — | todo | печатает |
| T-9-2 | закрытая задача | 1 | A | продукт | — | **done** (2026-08-19) | напечатала |
EOF
    cat > "$tmp/gaps.md" <<'EOF'
| ID | Статус | Вопрос | Гейт |
|---|---|---|---|
| Q-99 | OPEN | живой вопрос | T-9-1 |
EOF
    cat > "$tmp/state_bad.md" <<'EOF'
# 07 · STATE

## Подробности для модели

- **[якорь: T-9-1]** пункт с открытым якорем задачи
- **[якорь: Q-99]** пункт с открытым вопросом
- **[якорь: T-9-2]** пункт, у которого якорь закрыт
- **[якорь: T-9-2, Q-99]** пункт, где один якорь закрыт, второй открыт
- пункт без якоря вовсе
- **[якорь: T-9-7]** пункт с якорем, которого нет нигде

## Задачи и мандат

| Задача | Статус | Класс | Метка |
|---|---|---|---|
| T-9-2 закрытая задача | done | A | продукт |

## Следующая секция
- сюда проверка не заглядывает
EOF
    cat > "$tmp/state_ok.md" <<'EOF'
# 07 · STATE

## Подробности для модели

- **[якорь: T-9-1]** пункт с открытым якорем
- **[якорь: Q-99, T-9-2]** один якорь открыт — пункт горячий

## Задачи и мандат

| Задача | Статус | Класс | Метка |
|---|---|---|---|
| T-9-1 живая задача | todo | A | продукт |
| T-9-2 закрытая задача | done | A | продукт |

## Следующая секция
EOF

    check() {   # check <описание> <ожидаемое> <фактическое>
        if [ "$2" = "$3" ]; then
            passed=$((passed+1))
            echo "OK   $1: ожидалось [$2], получено [$3]"
        else
            failed=$((failed+1))
            echo "ПРОВАЛ $1: ожидалось [$2], получено [$3]"
        fi
    }

    out_bad="$(STATE_FILE="$tmp/state_bad.md" ROADMAP_FILE="$tmp/road.md" GAPS_FILE="$tmp/gaps.md" \
        CONTEXT_FILES="$tmp/state_bad.md" CONTEXT_LIMIT=10 run_check)"
    itog_bad="$(printf '%s\n' "$out_bad" | grep '^=== ИТОГ ===')"

    check "кейс 1 · пункт без якоря найден" \
        "1" "$(printf '%s\n' "$itog_bad" | sed -n 's/.*без якоря: \([0-9]*\).*/\1/p')"
    check "кейс 2 · пункт с закрытым якорем найден" \
        "1" "$(printf '%s\n' "$itog_bad" | sed -n 's/.*остывших: \([0-9]*\).*/\1/p')"
    check "кейс 3 · неразрешимый якорь найден" \
        "1" "$(printf '%s\n' "$itog_bad" | sed -n 's/.*неразрешимых: \([0-9]*\).*/\1/p')"
    check "кейс 4 · пункт со СМЕШАННЫМИ якорями остывшим НЕ считается" \
        "1" "$(printf '%s\n' "$out_bad" | grep -c 'пункт, у которого якорь закрыт')"
    check "кейс 5 · превышение порога названо" \
        "1" "$(printf '%s\n' "$out_bad" | grep -c 'ПОРОГ ПРЕВЫШЕН')"
    check "кейс 6 · секция за следующим заголовком не читается" \
        "0" "$(printf '%s\n' "$out_bad" | grep -c 'сюда проверка не заглядывает')"
    check "кейс 11 · открытая задача без строки мандата найдена (ADR-072)" \
        "1" "$(printf '%s\n' "$itog_bad" | sed -n 's/.*без мандата: \([0-9]*\).*/\1/p')"

    # Отрицательная проба: на исправной фикстуре все три класса дают НОЛЬ, и это
    # подтверждается напечатанными числами, а не отсутствием вывода.
    out_ok="$(STATE_FILE="$tmp/state_ok.md" ROADMAP_FILE="$tmp/road.md" GAPS_FILE="$tmp/gaps.md" \
        CONTEXT_FILES="$tmp/state_ok.md" CONTEXT_LIMIT=999999 run_check)"
    itog_ok="$(printf '%s\n' "$out_ok" | grep '^=== ИТОГ ===')"
    check "кейс 7 · исправная секция: без якоря 0" \
        "0" "$(printf '%s\n' "$itog_ok" | sed -n 's/.*без якоря: \([0-9]*\).*/\1/p')"
    check "кейс 8 · исправная секция: остывших 0" \
        "0" "$(printf '%s\n' "$itog_ok" | sed -n 's/.*остывших: \([0-9]*\).*/\1/p')"
    check "кейс 9 · исправная секция: неразрешимых 0" \
        "0" "$(printf '%s\n' "$itog_ok" | sed -n 's/.*неразрешимых: \([0-9]*\).*/\1/p')"
    check "кейс 10 · порог в норме назван положительным фактом" \
        "1" "$(printf '%s\n' "$out_ok" | grep -c 'в пределах порога')"
    check "кейс 12 · исправная таблица мандата: без мандата 0" \
        "0" "$(printf '%s\n' "$itog_ok" | sed -n 's/.*без мандата: \([0-9]*\).*/\1/p')"

    echo
    echo "=== САМОТЕСТ state_hot_check.sh: пройдено ${passed}, провалено ${failed} ==="
    [ "$failed" -eq 0 ]
}

case "${1:-}" in
    --selftest) selftest ;;
    *)
        repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
            echo "ОТКАЗ СРЕДЫ: не git-репозиторий"; exit 2; }
        cd "$repo_root" || exit 2
        run_check
        ;;
esac
