#!/usr/bin/env bash
# tools/intersect_check.sh <бриф1> <бриф2>
#
# Механическая проверка непересечения наборов «Файлы на запись» двух брифов
# (ADR-028, задача M-6a). Печатает оба набора целиком с указанием источника,
# обычные пересечения и отдельно — совпадения по общему сериализуемому
# ресурсу (ADR-028). На брифе без поля «Файлы на запись» печатает явный
# ОТКАЗ и завершается ненулевым кодом — не «пересечений нет».
set -u

SHARED_RESOURCES=(
  "07_STATE.md"
  "07_GAPS.md"
  "06_DECISIONS_LOG.md"
  "06_INDEX.md"
  "07_ARCHIVE.md"
)

if [ "$#" -ne 2 ]; then
  echo "Использование: tools/intersect_check.sh <бриф1> <бриф2>" >&2
  exit 2
fi

BRIEF_A="$1"
BRIEF_B="$2"

for f in "$BRIEF_A" "$BRIEF_B"; do
  if [ ! -f "$f" ]; then
    echo "ОТКАЗ: файл брифа не найден: $f"
    exit 3
  fi
done

# Извлекает блок «Файлы на запись» из брифа: от строки-заголовка
# `**Файлы на запись**` до следующей строки markdown-заголовка (`#...`)
# или конца файла. Из маркированных строк («- ...») берёт первый токен
# в обратных кавычках как путь.
extract_paths() {
  local brief="$1"
  awk '
    /^\*\*Файлы на запись\*\*/ { infield = 1; next }
    infield && /^#/ { infield = 0 }
    infield && /^-[[:space:]]/ {
      line = $0
      if (match(line, /`[^`]+`/)) {
        path = substr(line, RSTART + 1, RLENGTH - 2)
        print path
      }
    }
  ' "$brief"
}

PATHS_A="$(extract_paths "$BRIEF_A")"
PATHS_B="$(extract_paths "$BRIEF_B")"

REFUSED=0
if [ -z "$PATHS_A" ]; then
  echo "ОТКАЗ: у брифа $BRIEF_A нет поля «Файлы на запись» или список под ним пуст"
  REFUSED=1
fi
if [ -z "$PATHS_B" ]; then
  echo "ОТКАЗ: у брифа $BRIEF_B нет поля «Файлы на запись» или список под ним пуст"
  REFUSED=1
fi
if [ "$REFUSED" -eq 1 ]; then
  exit 1
fi

echo "=== Набор «Файлы на запись» — источник: $BRIEF_A ==="
while IFS= read -r p; do
  echo "$BRIEF_A: $p"
done <<< "$PATHS_A"

echo "=== Набор «Файлы на запись» — источник: $BRIEF_B ==="
while IFS= read -r p; do
  echo "$BRIEF_B: $p"
done <<< "$PATHS_B"

# Каталог со слэшем на конце поглощает вложенные файлы (08_TASK_BRIEF_TEMPLATE.md).
covers() {
  local dir="$1" path="$2"
  [[ "$dir" == */ && "$path" == "$dir"* ]]
}

is_shared_resource() {
  local path="$1"
  local name
  for name in "${SHARED_RESOURCES[@]}"; do
    if [ "$path" = "$name" ]; then
      return 0
    fi
  done
  return 1
}

REGULAR_COUNT=0
SHARED_COUNT=0
REGULAR_LINES=()
SHARED_LINES=()

while IFS= read -r pa; do
  [ -z "$pa" ] && continue
  while IFS= read -r pb; do
    [ -z "$pb" ] && continue
    MATCH=0
    if [ "$pa" = "$pb" ]; then
      MATCH=1
    elif covers "$pa" "$pb"; then
      MATCH=1
    elif covers "$pb" "$pa"; then
      MATCH=1
    fi
    if [ "$MATCH" -eq 1 ]; then
      if is_shared_resource "$pa" || is_shared_resource "$pb"; then
        SHARED_COUNT=$((SHARED_COUNT + 1))
        SHARED_LINES+=("общий сериализуемый ресурс (ADR-028): $pa ($BRIEF_A) = $pb ($BRIEF_B)")
      else
        REGULAR_COUNT=$((REGULAR_COUNT + 1))
        REGULAR_LINES+=("пересечение: $pa ($BRIEF_A) = $pb ($BRIEF_B)")
      fi
    fi
  done <<< "$PATHS_B"
done <<< "$PATHS_A"

echo "=== Пересечения ==="
echo "обычных пересечений: $REGULAR_COUNT"
for l in "${REGULAR_LINES[@]+"${REGULAR_LINES[@]}"}"; do
  echo "$l"
done

echo "=== Общий сериализуемый ресурс (ADR-028) ==="
echo "совпадений по общему ресурсу: $SHARED_COUNT"
for l in "${SHARED_LINES[@]+"${SHARED_LINES[@]}"}"; do
  echo "$l"
done

exit 0
