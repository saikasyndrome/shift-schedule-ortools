# Architecture

```text
config/sample.yaml
        │
        ▼
 ShiftGenerator          parse staff / rules / exceptions / OJT / prev_month
        │                  validate, summary, Excel export
        │
        ├─ engine: solver ──▶ ShiftSolver (CP-SAT) fills gen.result
        └─ engine: heuristic ──▶ randomized search (+ day backtrack)
        │
        ▼
 ExcelExporter → shift_YYYYMM_*.xlsx
```

## What YAML configures vs what code assumes

| In YAML | Hardcoded in Python |
|---|---|
| Staff roster, floors *assigned to people*, `rules.*` values, exceptions, OJT counts, schedule month/engine | Shift **code names** (`早1`/`遅1`/`早4`/`遅4`/`夜勤`/`明け`/`休み`/`有給`/`日勤`), balance/summary columns, daytime predicates, Excel legend text, and logic that keys off those strings |

`shift_types` in YAML still supplies hours/labels/`required`, but renaming the core codes without code changes will break matching, counts, and export.

## `shift_schedule.generator`

- Owns config parsing and result containers (`result`, `ojt_*`, `hard_errors`)
- Heuristic path: full regenerates + per-day redo; optional balance window
- Soft goals (leader daytime, OJT auto-match) warn; hard rule failures block export

## `shift_schedule.solver`

- Bool var per (staff, day, eligible shift code)
- Hard: exceptions, night chain, `no_late_to_early`, consecutive caps, exact `off_days`, night/required coverage, `max_nights`, OJT solo, `ojt_count`
- Soft (lexicographic): OJT counts → early/late balance → leader daytime
- `solve_alternatives`: collect equal-best solutions under a time budget
- On `INFEASIBLE`, relax diagnostic groups one-by-one to hint which rule set conflicts

## CLI

```bash
python -m shift_schedule config/sample.yaml
```
