#!/usr/bin/env bash
# tools/session_status.sh — состояние старта сессии одной командой (M-4, ADR-022).
# Пять счётчиков, каждый — число плюс совпавшие строки. Вердикт положительным счётчиком,
# не голым листингом: пусто и один служебный файл не должны выглядеть одинаково.
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "ОШИБКА: не git-репозиторий (git rev-parse --show-toplevel провалился)"
    exit 2
}
cd "$repo_root" || exit 2

dirty=0

echo "=== session_status.sh · $(date '+%Y-%m-%d %H:%M:%S') ==="
echo

# --- 1. Изменённые файлы -----------------------------------------------------
echo "-- 1. Изменённые файлы (git status, working tree + индекс) --"
changed_lines="$(git status --porcelain=v1)"
if [ -n "$changed_lines" ]; then
    changed_count=$(printf '%s\n' "$changed_lines" | awk 'END{print NR}')
else
    changed_count=0
fi
echo "count=${changed_count}"
if [ "$changed_count" -gt 0 ]; then
    printf '%s\n' "$changed_lines"
    dirty=1
fi
echo

# --- 2. Файлы буфера кроме служебного ----------------------------------------
# reference/_inbox/ — отложенная часть ADR-025 (Q-12), каталога пока нет.
# Отсутствие каталога — ожидаемое состояние в этом проекте, не отказ среды.
echo "-- 2. Файлы буфера session-блоков (reference/_inbox/), кроме .gitkeep --"
if [ -d "reference/_inbox" ]; then
    buffer_lines="$(find reference/_inbox -type f ! -name '.gitkeep' 2>/dev/null)"
    if [ -n "$buffer_lines" ]; then
        buffer_count=$(printf '%s\n' "$buffer_lines" | awk 'END{print NR}')
    else
        buffer_count=0
    fi
    echo "count=${buffer_count}"
    if [ "$buffer_count" -gt 0 ]; then
        printf '%s\n' "$buffer_lines"
        dirty=1
    fi
else
    echo "count=0"
    echo "буфер не заведён (отложенная часть ADR-025)"
fi
echo

# --- 3. Рабочие деревья --------------------------------------------------------
echo "-- 3. Рабочие деревья (git worktree list) --"
worktree_lines="$(git worktree list 2>/dev/null)"
worktree_total=$(printf '%s\n' "$worktree_lines" | awk 'NF{print NR}' | tail -1)
worktree_total=${worktree_total:-0}
# основное дерево не считается лишним; лишние — всё, кроме первой строки
worktree_extra=$(( worktree_total > 0 ? worktree_total - 1 : 0 ))
echo "count=${worktree_extra}"
printf '%s\n' "$worktree_lines"
if [ "$worktree_extra" -gt 0 ]; then
    dirty=1
fi
echo

# --- 4. Ветки сессий (s/*) -----------------------------------------------------
echo "-- 4. Ветки сессий (git branch --list 's/*') --"
branch_lines="$(git branch --list 's/*' 2>/dev/null)"
if [ -n "$branch_lines" ]; then
    branch_count=$(printf '%s\n' "$branch_lines" | awk 'END{print NR}')
else
    branch_count=0
fi
echo "count=${branch_count}"
if [ "$branch_count" -gt 0 ]; then
    printf '%s\n' "$branch_lines"
    dirty=1
fi
echo

# --- 5. Отставание от опубликованной ветки -------------------------------------
# Опубликованная ветка — origin/main (проверено: git remote -v печатает origin,
# origin/main присутствует).
echo "-- 5. Отставание/опережение относительно origin/main --"
if git rev-parse --verify -q origin/main >/dev/null; then
    lag_raw="$(git rev-list --left-right --count origin/main...HEAD 2>/dev/null)"
    behind=$(printf '%s' "$lag_raw" | awk '{print $1}')
    ahead=$(printf '%s' "$lag_raw" | awk '{print $2}')
    behind=${behind:-0}
    ahead=${ahead:-0}
    lag_count=$(( behind + ahead ))
    echo "count=${lag_count}"
    echo "позади origin/main: ${behind}; впереди origin/main: ${ahead}"
    if [ "$lag_count" -gt 0 ]; then
        git log --oneline origin/main...HEAD 2>/dev/null
        dirty=1
    fi
else
    echo "count=0"
    echo "origin/main не найдена — CONTEXT GAP для этого счётчика"
    dirty=1
fi
echo

echo "=== ВЕРДИКТ ==="
if [ "$dirty" -eq 0 ]; then
    echo "ЧИСТО"
    exit 0
else
    echo "НЕ ЧИСТО"
    exit 1
fi
