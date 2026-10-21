# Config reference

Sample file: [`config/sample.yaml`](../config/sample.yaml).

**Scope:** YAML sets *values* (who works where, caps, exceptions). The *shift vocabulary* (`早1`/`遅1`/`早4`/`遅4`/`夜勤`/`明け`/`休み`/`有給`/`日勤` and ward strings used in balance/summary/legend) is assumed by the Python code — see [architecture.md](architecture.md).

## `schedule`

| Key | Default | Notes |
|---|---|---|
| `year` / `month` | — | Target calendar month (`num_days` is derived) |
| `engine` | `solver` | `solver` = OR-Tools CP-SAT; `heuristic` = seed retry search |
| `seed` | `1` | Reproducibility / which feasible solution to pick |
| `attempts` | `1000` | Heuristic only: full regenerate budget (early-stop after ~300 stagnant tries) |
| `day_attempts` | `30` | Heuristic only: per-day partial redo budget |
| `balance_seconds` | `0` | Extra search time for early/late balance after first feasible hit |
| `alternatives` | `1` | Solver only: how many equal-best Excel files to emit |
| `alternatives_seconds` | `20` | Time budget for collecting tied solutions |

OJT target fulfillment is ranked above early/late balance when comparing candidates.

## `staff[]`

| Key | Notes |
|---|---|
| `name` | Referenced by `exceptions` / `ojt` / `prev_month` |
| `floor` | List of floors. String → early+late; `{floor, type: early\|late}` → one type |
| `night_ok` | Eligible for `夜勤` |
| `day_ok` | May receive `日勤` via `exceptions` only (never auto-picked). Default `false` |
| `leader` | Prefer ≥1 leader on daytime duty. Default `false` |
| `max_nights` | Cap on night shifts this month |
| `max_consecutive` | Optional personal override of `rules.max_consecutive` |
| `note` | Free text; ignored by logic |
| `ojt_teacher` | Floor(s) this person can teach (`floor_a` / `floor_b` / `夜勤`, or typed objects / lists) |
| `ojt_target` | Floor(s) for training. Solo eligibility still follows `staff.floor` |
| `ojt_count` | Hard monthly OJT target (like `off_days`). Omit → soft “as many as matched” |

**OJT solo rule:** if a floor appears only under `ojt_target` (not in `floor`), the person may be assigned that floor only when paired with a teacher. If it also appears in `floor`, they may work alone; paired days get an `(OJT)` label for counting.

## `shift_types[]`

| Key | Notes |
|---|---|
| `code` | Display / assignment key. Core codes `早1` `遅1` `早4` `遅4` `夜勤` `明け` `休み` `有給` `日勤` are **string-matched in code** (not fully data-driven) — renaming without code edits breaks the engine |
| `name` | Label only |
| `start` / `end` | Display only |
| `hours` | Used in total-hours summary |
| `floor` | Ward / `both` for nights; omit for offs |
| `type` | `early` \| `late` \| `day` \| `night` \| `off_after_night` \| `off` |
| `required` | If `true`, ≥1 assignee every day (hard). Not used for `日勤` |

`明け` / `休み` are chain-assigned after nights, not freely chosen. `日勤` is exceptions-only.

## `rules`

All hard. Failure → no Excel, exit `1`.

| Key | Notes |
|---|---|
| `max_consecutive` | Max consecutive work days (staff override allowed) |
| `off_days` | **Required.** Exact pure-off day count per person (`明け`/`有給`/OJT excluded; `exceptions type: 休み` counts) |
| `night_required_per_day` | Default `1` |
| `max_consecutive_off` | Default `2`; exceptions can intentionally exceed |
| `no_late_to_early` | Block late → early (and day treated as both sides of that rule) |

Unused today (kept for compatibility): `night_set`, `min_leader_daytime`.

Leader daytime preference and auto-OJT matching are soft (warnings only).

## `ojt` (optional)

Manual OJT pins:

```yaml
ojt:
  - date: "2026-09-10"
    staff:
      - name: Alice
        shift: 遅4
```

Hard rules and the night→明け→休み chain always win; blocked OJT becomes a warning. Counts toward `ojt_count`; shortage is auto-matched.

## `exceptions[]`

| `type` | Effect |
|---|---|
| `休み` | Forced off; counts toward `off_days` |
| `有給` | Forced PTO label; does **not** count toward `off_days` |
| `夜勤不可` | Exclude nights that day only |
| shift `code` | Pin that code (`日勤` only via exception; needs `day_ok`) |

Optional `reason` is ignored by logic. Pins yield to hard rules / floor / night caps (warning).

## `prev_month` (optional)

Recent end-of-previous-month codes for day-1 consecutive / late→early checks:

```yaml
prev_month:
  - name: Alice
    last_shifts: [早4, 早4, 遅4, 早4, 夜勤]  # oldest → month-end; last 5 used
```
