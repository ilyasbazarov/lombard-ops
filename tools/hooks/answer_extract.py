# tools/hooks/answer_extract.py — выемка последнего ответа роли из транскрипта (ADR-074 §1).
#
# Используется обеими проверками ответа (answer_check.sh, answer_judge.sh), чтобы разбор
# транскрипта лежал в ОДНОМ месте: две копии разъезжаются молча, и это уже стоило проекту
# дубля записи в журнале изменений, который никто не заметил три недели (_APPLIER.md).
#
# Вход: JSON хука Stop на stdin, путь выходного файла первым аргументом.
# Коды выхода: 0 — текст записан; 4 — текст записан, но это ПОВТОРНЫЙ заход (stop_hook_active);
#              1 — payload или транскрипт не разобраны (для вызывающего это гэп наблюдения,
#                  а не факт «нарушений нет»: 05 §I, «Успех инструмента ≠ факт»).
import io
import json
import sys

out_path = sys.argv[1]
try:
    payload = json.loads(sys.stdin.read())
except Exception:
    sys.exit(1)

# Повторный заход. Текст извлекается и на втором проходе — иначе замер видит ФАКТ возврата,
# но не его ИСХОД, а правило-останов, удостоверяемое только первой веткой, признаком не
# является (05 §I, правила наблюдения). Код 4 велит проверке идти в предупредительном
# режиме: вердикт пишется в лог, ответ не возвращается, пара «хук ↔ модель» в цикл не уходит.
repeat = bool(payload.get("stop_hook_active"))

last = ""
try:
    with io.open(payload.get("transcript_path") or "", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "assistant":
                continue
            blocks = (obj.get("message") or {}).get("content") or []
            text = "\n".join(
                b.get("text", "") for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if text:
                last = text
except Exception:
    sys.exit(1)

with io.open(out_path, "w", encoding="utf-8") as fh:
    fh.write(last)

sys.exit(4 if repeat else 0)
