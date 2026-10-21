"""Regression checks: python tests/test_solver.py"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import copy

from shift_schedule.generator import load_config
from shift_schedule.solver import ShiftSolver

def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  OK: {msg}")

def test_real_config_zero_hard_errors():
    print("\n[1] 実際のconfig/sample.yamlで絶対ルール違反0件になるか")
    cfg = load_config("config/sample.yaml")
    for s in cfg["staff"]:
        if s.get("ojt_target") and s.get("ojt_count"):
            s["ojt_count"] = 1
    solver = ShiftSolver(cfg)
    gen, success = solver.solve(balance_seconds=0, feasibility_time_limit=30)
    check(success, "solve()がsuccess=Trueを返す")
    check(len(gen.hard_errors) == 0, f"hard_errorsが0件 (実際: {gen.hard_errors})")
    return gen

def test_night_chain(gen):
    print("\n[2] 夜勤→明け→休み(有給)体制が全員・全日で守られているか")
    for s in gen.staff:
        name = s["name"]
        for day in range(1, gen.num_days):
            today = gen.base_code(gen.result[name].get(day, ""))
            tomorrow = gen.base_code(gen.result[name].get(day + 1, ""))
            if today == "夜勤":
                check(tomorrow == "明け", f"{name} {day}日夜勤 → {day+1}日は明けのはず (実際: {tomorrow})")
        for day in range(1, gen.num_days):
            today = gen.base_code(gen.result[name].get(day, ""))
            if today == "明け":
                tomorrow_raw = gen.result[name].get(day + 1, "")
                tomorrow = gen.base_code(tomorrow_raw)
                check(
                    tomorrow in ("休み", "有給"),
                    f"{name} {day}日明け → {day+1}日は休み/有給のはず (実際: {tomorrow_raw})",
                )

def test_no_late_to_early(gen):
    print("\n[3] no_late_to_early (遅番/日勤の翌日に早番・日勤が来ないか)")
    for s in gen.staff:
        name = s["name"]
        for day in range(1, gen.num_days):
            today = gen.base_code(gen.result[name].get(day, ""))
            tomorrow = gen.base_code(gen.result[name].get(day + 1, ""))
            if gen.is_late(today):
                check(
                    not (gen.is_early(tomorrow) or tomorrow == "日勤"),
                    f"{name} {day}日{today} → {day+1}日{tomorrow} は禁止のはず",
                )
            if today == "日勤":
                check(
                    not gen.is_early(tomorrow),
                    f"{name} {day}日日勤 → {day+1}日{tomorrow} は禁止のはず",
                )

def test_max_consecutive_off(gen):
    print("\n[4b] max_consecutive_off (exceptionsで明示指定していない連続休み・有給は上限以内か)")
    cap = gen.rules.get("max_consecutive_off", 2)
    for s in gen.staff:
        name = s["name"]
        streak_days = []

        def _flush():
            if len(streak_days) > cap:
                has_exc = any(gen.is_exception(name, d) for d in streak_days)
                check(
                    has_exc,
                    f"{name} の{streak_days}連続休み・有給(上限{cap}日超)はexceptionsで明示指定されているはず",
                )

        for day in range(1, gen.num_days + 1):
            code = gen.base_code(gen.result[name].get(day, ""))
            if code in ("休み", "有給"):
                streak_days.append(day)
            else:
                _flush()
                streak_days = []
        _flush()

def test_off_days_exact(gen):
    print("\n[4] off_days が全員ぴったり一致しているか")
    off_target = gen.rules["off_days"]
    for s in gen.staff:
        name = s["name"]
        off_count = sum(1 for d in range(1, gen.num_days + 1) if gen.result[name].get(d) == "休み")
        check(off_count == off_target, f"{name}の休み日数が{off_target}日 (実際: {off_count}日)")

def test_max_consecutive(gen):
    print("\n[5] max_consecutive を超える連続勤務がないか")
    for s in gen.staff:
        name = s["name"]
        mc = s.get("max_consecutive", gen.rules["max_consecutive"])
        streak = 0
        max_streak = 0
        for day in range(1, gen.num_days + 1):
            code = gen.result[name].get(day, "")
            is_work = code not in ("", "休み", "明け", "有給", "?")
            streak = streak + 1 if is_work else 0
            max_streak = max(max_streak, streak)
        check(max_streak <= mc, f"{name}の最大連続勤務日数が{mc}日以内 (実際: {max_streak}日)")

def test_night_required_and_max_nights(gen):
    print("\n[6] night_required_per_day / max_nights")
    night_required = gen.rules.get("night_required_per_day", 1)
    for day in range(1, gen.num_days + 1):
        count = sum(1 for s in gen.staff if gen.result[s["name"]].get(day) == "夜勤")
        check(count >= night_required, f"{day}日の夜勤人数が{night_required}人以上 (実際: {count}人)")
    for s in gen.staff:
        name = s["name"]
        max_n = s.get("max_nights", 99)
        count = sum(1 for d in range(1, gen.num_days + 1) if gen.result[name].get(d) == "夜勤")
        check(count <= max_n, f"{name}の夜勤回数が{max_n}回以内 (実際: {count}回)")

def test_required_coverage(gen):
    print("\n[7] required系コードの毎日最低1名カバレッジ")
    for code in gen.required_codes:
        for day in range(1, gen.num_days + 1):
            count = sum(1 for s in gen.staff if gen.base_code(gen.result[s["name"]].get(day, "")) == code)
            check(count >= 1, f"{day}日の{code}が最低1名 (実際: {count}人)")

def test_ojt_solo_restriction(gen):
    print("\n[8] ojt_targetのみで一人勤務できないコードが、マッチ無しの日に発生していないか")
    solver = ShiftSolver.__new__(ShiftSolver)
    solver.config = gen.config
    solver.gen = gen
    solver.staff = gen.staff
    solver.num_days = gen.num_days
    solver.rules = gen.rules
    solver.shift_map = gen.shift_map
    solver.required_codes = gen.required_codes
    solver.night_required = gen.rules.get("night_required_per_day", 1)
    solver.off_target = gen.rules["off_days"]
    solver.early_codes = [c for c, s in gen.shift_map.items() if s.get("type") == "early"]
    solver.late_codes = [c for c, s in gen.shift_map.items() if s.get("type") == "late"]
    solver.day_codes = [c for c, s in gen.shift_map.items() if s.get("type") == "day"]
    night_codes = [c for c, s in gen.shift_map.items() if s.get("type") == "night"]
    solver.night_code = night_codes[0] if night_codes else "夜勤"

    for s in gen.staff:
        name = s["name"]
        restricted = solver._ojt_restricted_codes(s)
        if not restricted:
            continue
        for day in range(1, gen.num_days + 1):
            raw = gen.result[name].get(day, "")
            code = gen.base_code(raw)
            if code in restricted:
                check(
                    raw.endswith("(OJT)"),
                    f"{name} {day}日 {code} はOJTマッチが無いと一人でできないはず (実際: {raw})",
                )

def test_seed_reproducibility():
    print("\n[10] seedの再現性 (同じseedなら同じ結果、違うseedなら別の結果)")
    cfg = load_config("config/sample.yaml")
    for s in cfg["staff"]:
        if s.get("ojt_target") and s.get("ojt_count"):
            s["ojt_count"] = 1

    def run(seed):
        solver = ShiftSolver(cfg)
        gen, success = solver.solve(balance_seconds=0, feasibility_time_limit=30, seed=seed)
        check(success, f"seed={seed}で絶対ルール違反なく生成できるはず")
        return tuple(gen.result[s["name"]].get(d) for s in gen.staff for d in range(1, gen.num_days + 1))

    r1a = run(1)
    r1b = run(1)
    r2 = run(2)
    check(r1a == r1b, "同じseed(1)なら2回とも完全に同じ結果になるはず")
    check(r1a != r2, "seedを変えると(1→2)結果が変わるはず")

def test_ojt_count_hard_error():
    print("\n[11] ojt_count が達成不可能な値のとき、こっそり減らさずハードエラーになるか")
    cfg = load_config("config/sample.yaml")

    cfg_a = copy.deepcopy(cfg)
    for s in cfg_a["staff"]:
        if s["name"] == "Frank":
            s["ojt_count"] = 999
    solver_a = ShiftSolver(cfg_a)
    gen_a, ok_a = solver_a.solve(balance_seconds=0, feasibility_time_limit=15)
    check(not ok_a, "稼働日数を超えるojt_countはsuccess=Falseになるはず")
    check(len(gen_a.hard_errors) >= 1, "ojt_countの説明を含むhard_errorsが返るはず")

    cfg_b = copy.deepcopy(cfg)
    for s in cfg_b["staff"]:
        if s["name"] == "Frank":
            s["ojt_count"] = 3
    solver_b = ShiftSolver(cfg_b)
    gen_b, ok_b = solver_b.solve(balance_seconds=0, feasibility_time_limit=30, seed=5)
    check(not ok_b, "現状のルール構成ではFrankのojt_count=3は満たせずsuccess=Falseになるはず")
    check(
        any("ojt_count" in e for e in gen_b.hard_errors),
        "診断メッセージにojt_countが含まれるはず(こっそり1回等に減らされていないか確認)",
    )

def test_infeasible_diagnostics():
    print("\n[9] INFEASIBLEな設定で診断メッセージが出るか")
    cfg = load_config("config/sample.yaml")
    cfg2 = copy.deepcopy(cfg)
    cfg2["rules"]["night_required_per_day"] = 6
    solver = ShiftSolver(cfg2)
    gen, success = solver.solve(balance_seconds=0, feasibility_time_limit=15)
    check(not success, "night_required_per_day=6は実行不可能と判定されるはず")
    check(len(gen.hard_errors) >= 2, "INFEASIBLEの説明 + 診断メッセージが返るはず")
    check(
        any("night_required_per_day" in e for e in gen.hard_errors),
        "診断メッセージにnight_required_per_dayが含まれるはず",
    )

def test_solve_alternatives():
    print("\n[12] solve_alternatives: タイになる別解を複数返せるか")
    cfg = load_config("config/sample.yaml")
    for s in cfg["staff"]:
        if s.get("ojt_target") and s.get("ojt_count"):
            s["ojt_count"] = 1
    solver = ShiftSolver(cfg)
    gens, ok = solver.solve_alternatives(
        count=2, balance_seconds=0, seed=1, alternatives_seconds=15
    )
    check(ok, "solve_alternatives()がsuccess=Trueを返す")
    check(len(gens) >= 1, "少なくとも1つは解が返る")
    for g in gens:
        check(len(g.hard_errors) == 0, f"各解のhard_errorsが0件 (実際: {g.hard_errors})")
    if len(gens) > 1:
        diffs = sum(
            1
            for s in gens[0].staff
            for d in range(1, gens[0].num_days + 1)
            if gens[0].result[s["name"]].get(d) != gens[1].result[s["name"]].get(d)
        )
        check(diffs > 0, "2つ目の別解は1つ目と少なくとも1マスは異なるはず")
        summaries = [{r["name"]: (r["work"], r["nights"]) for r in g.summary()} for g in gens]
        check(
            summaries[0] == summaries[1],
            "別解同士は日々の割当が違っても、出勤日数・夜勤回数などの集計は同じ(タイ)はず",
        )

if __name__ == "__main__":
    gen = test_real_config_zero_hard_errors()
    test_night_chain(gen)
    test_no_late_to_early(gen)
    test_max_consecutive_off(gen)
    test_off_days_exact(gen)
    test_max_consecutive(gen)
    test_night_required_and_max_nights(gen)
    test_required_coverage(gen)
    test_ojt_solo_restriction(gen)
    test_seed_reproducibility()
    test_ojt_count_hard_error()
    test_infeasible_diagnostics()
    test_solve_alternatives()
    print("\n✅ 全テスト成功")
