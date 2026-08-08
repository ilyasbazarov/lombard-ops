# M-6a — замер `tools/intersect_check.sh` на реальных брифах репозитория

**Дата:** 2026-08-08 · **Задача:** M-6a · **Коммит на входе:** ca07920 (`git rev-parse HEAD`)

Каталог `briefs/` на момент исполнения (`ls briefs/`): `M-1.md`, `M-3.md`, `M-4.md`, `M-6a.md`,
`T-0-10.md`, `T-0-2.md`, `T-0-3.md`, `T-0-5.md`, `_GENERATOR.md`.

Три лога ниже — полный вывод команд, не пересказ.

---

## Лог 1 — позитивный случай (пара актуального формата, ноль пересечений)

Команда: `tools/intersect_check.sh briefs/M-1.md briefs/M-3.md`

```
=== Набор «Файлы на запись» — источник: briefs/M-1.md ===
briefs/M-1.md: .claude/settings.json
briefs/M-1.md: .claude/agents/architect.md
briefs/M-1.md: .claude/agents/generator.md
briefs/M-1.md: .claude/agents/executor.md
briefs/M-1.md: reference/M-1_mandate_measurement_<дата>.md
=== Набор «Файлы на запись» — источник: briefs/M-3.md ===
briefs/M-3.md: reference/M-3_canon_sweep_<дата>.md
briefs/M-3.md: reference/M-3_schema_fingerprint_assertions_<дата>.md
=== Пересечения ===
обычных пересечений: 0
=== Общий сериализуемый ресурс (ADR-028) ===
совпадений по общему ресурсу: 0
exit code: 0
```

Вердикт: оба набора напечатаны целиком с источником, обычных пересечений — 0, положительным
счётчиком.

---

## Лог 2 — случай ОТКАЗа (один бриф старого формата)

Команда: `tools/intersect_check.sh briefs/M-1.md briefs/T-0-2.md`

```
ОТКАЗ: у брифа briefs/T-0-2.md нет поля «Файлы на запись» или список под ним пуст
exit code: 1
```

Вердикт: скрипт печатает явную строку ОТКАЗА для брифа `T-0-2.md` (поля «Файлы на запись» в старом
формате нет) и завершается ненулевым кодом. Строки «пересечений нет» не печатается.

Дополнительно — контрольная пара, где ОБА брифа старого формата
(`tools/intersect_check.sh briefs/T-0-3.md briefs/T-0-5.md`), подтверждает исправность отказа на
обеих сторонах пары:

```
ОТКАЗ: у брифа briefs/T-0-3.md нет поля «Файлы на запись» или список под ним пуст
ОТКАЗ: у брифа briefs/T-0-5.md нет поля «Файлы на запись» или список под ним пуст
exit code: 1
```

---

## Лог 3 — общий сериализуемый ресурс (ADR-028): факт замера

Пять имён общего ресурса (`08_TASK_BRIEF_TEMPLATE.md`): `07_STATE.md`, `07_GAPS.md`,
`06_DECISIONS_LOG.md`, `06_INDEX.md`, `07_ARCHIVE.md`.

Прогнаны все три пары реальных брифов актуального формата, доступные в каталоге на момент замера
(`M-1`, `M-3`, `M-4`):

Команда: `tools/intersect_check.sh briefs/M-1.md briefs/M-4.md`

```
=== Набор «Файлы на запись» — источник: briefs/M-1.md ===
briefs/M-1.md: .claude/settings.json
briefs/M-1.md: .claude/agents/architect.md
briefs/M-1.md: .claude/agents/generator.md
briefs/M-1.md: .claude/agents/executor.md
briefs/M-1.md: reference/M-1_mandate_measurement_<дата>.md
=== Набор «Файлы на запись» — источник: briefs/M-4.md ===
briefs/M-4.md: tools/session_status.sh
briefs/M-4.md: tools/hooks/pre-commit
briefs/M-4.md: tools/hooks/selftest.sh
briefs/M-4.md: reference/M-4_hook_measurement_2026-XX-XX.md
=== Пересечения ===
обычных пересечений: 0
=== Общий сериализуемый ресурс (ADR-028) ===
совпадений по общему ресурсу: 0
exit code: 0
```

Команда: `tools/intersect_check.sh briefs/M-3.md briefs/M-4.md`

```
=== Набор «Файлы на запись» — источник: briefs/M-3.md ===
briefs/M-3.md: reference/M-3_canon_sweep_<дата>.md
briefs/M-3.md: reference/M-3_schema_fingerprint_assertions_<дата>.md
=== Набор «Файлы на запись» — источник: briefs/M-4.md ===
briefs/M-4.md: tools/session_status.sh
briefs/M-4.md: tools/hooks/pre-commit
briefs/M-4.md: tools/hooks/selftest.sh
briefs/M-4.md: reference/M-4_hook_measurement_2026-XX-XX.md
=== Пересечения ===
обычных пересечений: 0
=== Общий сериализуемый ресурс (ADR-028) ===
совпадений по общему ресурсу: 0
exit code: 0
```

**Факт замера:** ни в одной из трёх пар реальных брифов актуального формата (`M-1`×`M-3`,
`M-1`×`M-4`, `M-3`×`M-4`), присутствующих в каталоге `briefs/` на дату замера, совпадения по
одному из пяти имён общего сериализуемого ресурса не найдено — счётчик «совпадений по общему
ресурсу» равен 0 во всех трёх запусках. Ни один из шести объявленных в этих брифах путей на запись
не входит в пятёрку `07_STATE.md`, `07_GAPS.md`, `06_DECISIONS_LOG.md`, `06_INDEX.md`,
`07_ARCHIVE.md`. Синтетическая пара под этот случай не сочинялась (запрещено брифом) — категория
в коде реализована и печатается (метка «общий сериализуемый ресурс (ADR-028)» отдельной строкой,
см. Лог 1/3), но на реальном входе текущего репозитория не сработала ни разу.

--- END M-6a_intersect_measurement_2026-08-08.md ---
