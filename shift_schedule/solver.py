"""OR-Tools CP-SAT assignment engine. See docs/architecture.md."""

from ortools.sat.python import cp_model

from shift_schedule.generator import ShiftGenerator

class _AlternativeSolutionCollector(cp_model.CpSolverSolutionCallback):

    def __init__(self, x, ojt_match, limit):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self._x = x
        self._ojt_match = ojt_match
        self._limit = limit
        self.solutions = []

    def on_solution_callback(self):
        x_vals = {k: self.Value(v) for k, v in self._x.items()}
        ojt_vals = {k: self.Value(v) for k, v in self._ojt_match.items()}
        self.solutions.append((x_vals, ojt_vals))
        if len(self.solutions) >= self._limit:
            self.StopSearch()

DIAG_GROUPS = [
    ("night_required",    "night_required_per_day(夜勤最低人数)"),
    ("off_days_exact",     "off_days(休み日数を正確に合わせる制約)"),
    ("required_coverage",  "required系コード(早1/遅1/早4/遅4)の毎日最低1名カバレッジ"),
    ("max_consecutive",    "max_consecutive(最大連続勤務日数)"),
    ("max_consecutive_off", "max_consecutive_off(連続休み・有給の上限)"),
    ("ojt_solo",            "OJT対象者の一人勤務禁止(solo)制限"),
    ("max_nights",          "max_nights(個人ごとの夜勤最大回数)"),
    ("ojt_count",            "ojt_count(OJT目標回数を必ず満たす制約)"),
]

class ShiftSolver:
    def __init__(self, config):
        self.config = config
        self.gen = ShiftGenerator(config)
        self.staff        = self.gen.staff
        self.num_days     = self.gen.num_days
        self.rules        = self.gen.rules
        self.shift_map    = self.gen.shift_map
        self.required_codes = self.gen.required_codes
        self.night_required = self.rules.get("night_required_per_day", 1)
        self.off_target    = self.rules["off_days"]

        self.early_codes = [c for c, s in self.shift_map.items() if s.get("type") == "early"]
        self.late_codes  = [c for c, s in self.shift_map.items() if s.get("type") == "late"]
        self.day_codes   = [c for c, s in self.shift_map.items() if s.get("type") == "day"]
        night_codes      = [c for c, s in self.shift_map.items() if s.get("type") == "night"]
        self.night_code  = night_codes[0] if night_codes else "夜勤"

    def _base_capable(self, staff_info, code):
        if code == self.night_code:
            return bool(staff_info.get("night_ok", False))
        if code in self.day_codes:
            return bool(staff_info.get("day_ok", False))
        return self.gen.can_assign_code(staff_info, code)

    def _ojt_restricted_codes(self, staff_info):
        raw = staff_info.get("ojt_target")
        if not raw:
            return set()
        restricted = set()
        for floor, type_ in self.gen.parse_ojt_entries(raw):
            for c in self.gen.ojt_floor_codes(floor, type_):
                if not self._base_capable(staff_info, c):
                    restricted.add(c)
        return restricted

    def _person_codes_for_day(self, staff_info, day):
        name = staff_info["name"]
        exc = self.gen.is_exception(name, day)
        codes = set()
        for c in self.early_codes + self.late_codes:
            if self._base_capable(staff_info, c):
                codes.add(c)
        if staff_info.get("night_ok"):
            codes.add(self.night_code)
        codes |= self._ojt_restricted_codes(staff_info)
        codes.add("休み")
        codes.add("明け")
        if exc and exc["type"] == "有給":
            codes.add("有給")
        if exc and exc["type"] == "日勤" and staff_info.get("day_ok"):
            codes.add("日勤")
        if exc and exc["type"] == "夜勤不可":
            codes.discard(self.night_code)
        return codes

    def _prev_indicator(self, x, name, day, code):
        if day >= 1:
            return x.get((name, day, code))
        return 1 if self.gen.result[name].get(day, "") == code else 0

    def _forbid_if_indicator(self, model, var_to_forbid, indicator):
        if indicator is None:
            return
        if isinstance(indicator, int):
            if indicator == 1:
                model.Add(var_to_forbid == 0)
            return
        model.Add(var_to_forbid == 0).OnlyEnforceIf(indicator)

    def _ojt_pair_candidates(self):
        pairs = []
        for target in self.staff:
            if not target.get("ojt_target"):
                continue
            target_entries = self.gen.parse_ojt_entries(target["ojt_target"])
            floor_codes = {}
            for floor, type_ in target_entries:
                codes = self.gen.ojt_floor_codes(floor, type_)
                if codes:
                    floor_codes[floor] = (codes, type_)
            if not floor_codes:
                continue
            for teacher in self.staff:
                if teacher["name"] == target["name"] or not teacher.get("ojt_teacher"):
                    continue
                for t_floor, t_type in self.gen.parse_ojt_entries(teacher["ojt_teacher"]):
                    if t_floor not in floor_codes:
                        continue
                    codes, _target_type = floor_codes[t_floor]
                    pair_codes = [
                        c for c in codes
                        if t_type is None or self.shift_map.get(c, {}).get("type") == t_type
                    ]
                    for c in pair_codes:
                        pairs.append((target["name"], teacher["name"], c))
        return pairs

    def _build_model(self, relax=frozenset()):
        model = cp_model.CpModel()
        x = {}
        codes_by_person_day = {}
        ignored_exception_warnings = []

        for s in self.staff:
            name = s["name"]
            for day in range(1, self.num_days + 1):
                codes = self._person_codes_for_day(s, day)
                codes_by_person_day[(name, day)] = codes
                for c in codes:
                    x[(name, day, c)] = model.NewBoolVar(f"x_{name}_{day}_{c}")
                model.AddExactlyOne(x[(name, day, c)] for c in codes)

        for s in self.staff:
            name = s["name"]
            for day in range(1, self.num_days + 1):
                exc = self.gen.is_exception(name, day)
                if not exc:
                    continue
                t = exc["type"]
                if t in ("休み", "有給"):
                    model.Add(x[(name, day, t)] == 1)
                elif t == "夜勤不可":
                    continue  # _person_codes_for_dayで既に候補から除外済み
                elif t in self.shift_map:
                    if (name, day, t) in x:
                        model.Add(x[(name, day, t)] == 1)
                    else:
                        ignored_exception_warnings.append(
                            f"⚠ {name} {day}日: 例外({t}指定)予定でしたが適性"
                            f"(floor/night_ok/day_ok)を満たさないため無視されました"
                        )

        for s in self.staff:
            name = s["name"]
            for day in range(1, self.num_days + 1):
                prev_night = self._prev_indicator(x, name, day - 1, self.night_code)
                ake_var = x.get((name, day, "明け"))
                if ake_var is not None:
                    model.Add(ake_var == (prev_night if prev_night is not None else 0))

                prev_ake = self._prev_indicator(x, name, day - 1, "明け")
                for c in codes_by_person_day[(name, day)]:
                    if c in ("休み", "有給", "明け"):
                        continue
                    self._forbid_if_indicator(model, x[(name, day, c)], prev_ake)

        if self.rules.get("no_late_to_early"):
            for s in self.staff:
                name = s["name"]
                for day in range(1, self.num_days + 1):
                    late_vars = [x[(name, day, c)] for c in self.late_codes if (name, day, c) in x]
                    if late_vars and day + 1 <= self.num_days:
                        next_forbidden = [
                            c for c in self.early_codes + self.day_codes
                            if (name, day + 1, c) in x
                        ]
                        for lv in late_vars:
                            for nc in next_forbidden:
                                model.Add(lv + x[(name, day + 1, nc)] <= 1)

                    day_vars = [x[(name, day, c)] for c in self.day_codes if (name, day, c) in x]
                    if day_vars and day + 1 <= self.num_days:
                        next_forbidden_early = [c for c in self.early_codes if (name, day + 1, c) in x]
                        for dv in day_vars:
                            for nc in next_forbidden_early:
                                model.Add(dv + x[(name, day + 1, nc)] <= 1)

                prev0 = self.gen.result[name].get(0, "")
                prev0_type = self.shift_map.get(prev0, {}).get("type")
                if prev0_type == "late":
                    for c in self.early_codes + self.day_codes:
                        if (name, 1, c) in x:
                            model.Add(x[(name, 1, c)] == 0)
                elif prev0_type == "day":
                    for c in self.early_codes:
                        if (name, 1, c) in x:
                            model.Add(x[(name, 1, c)] == 0)

        work = {}
        for s in self.staff:
            name = s["name"]
            for day in range(1, self.num_days + 1):
                off_vars = [x[(name, day, c)] for c in ("休み", "明け", "有給") if (name, day, c) in x]
                w = model.NewBoolVar(f"work_{name}_{day}")
                model.Add(w == 1 - sum(off_vars))
                work[(name, day)] = w

        if "max_consecutive" not in relax:
            for s in self.staff:
                name = s["name"]
                mc = s.get("max_consecutive", self.rules["max_consecutive"])
                for start in range(-4, self.num_days - mc + 1):
                    terms = []
                    for d in range(start, start + mc + 1):
                        if d < 1:
                            terms.append(
                                1 if self.gen.result[name].get(d, "") not in ("", "休み", "明け", "有給", "?") else 0
                            )
                        else:
                            terms.append(work[(name, d)])
                    model.Add(sum(terms) <= mc)

        if "max_consecutive_off" not in relax:
            off_cap = self.rules.get("max_consecutive_off", 2)
            for s in self.staff:
                name = s["name"]
                for start in range(-off_cap, self.num_days - off_cap):
                    window = range(start, start + off_cap + 1)
                    forced = any(
                        d >= 1
                        and (exc := self.gen.is_exception(name, d))
                        and exc["type"] in ("休み", "有給")
                        for d in window
                    )
                    if forced:
                        continue
                    terms = []
                    for d in window:
                        if d < 1:
                            terms.append(1 if self.gen.result[name].get(d, "") in ("休み", "有給") else 0)
                        else:
                            off_here = [x[(name, d, c)] for c in ("休み", "有給") if (name, d, c) in x]
                            terms.append(sum(off_here) if off_here else 0)
                    model.Add(sum(terms) <= off_cap)

        if "off_days_exact" not in relax:
            for s in self.staff:
                name = s["name"]
                off_vars = [x[(name, day, "休み")] for day in range(1, self.num_days + 1)]
                model.Add(sum(off_vars) == self.off_target)

        if "night_required" not in relax:
            for day in range(1, self.num_days + 1):
                night_vars = [
                    x[(s["name"], day, self.night_code)]
                    for s in self.staff if (s["name"], day, self.night_code) in x
                ]
                model.Add(sum(night_vars) >= self.night_required)

        if "required_coverage" not in relax:
            for code in self.required_codes:
                for day in range(1, self.num_days + 1):
                    vars_ = [x[(s["name"], day, code)] for s in self.staff if (s["name"], day, code) in x]
                    if vars_:
                        model.Add(sum(vars_) >= 1)

        if "max_nights" not in relax:
            for s in self.staff:
                name = s["name"]
                max_n = s.get("max_nights", 99)
                night_vars = [x[(name, day, self.night_code)] for day in range(1, self.num_days + 1)
                              if (name, day, self.night_code) in x]
                if night_vars:
                    model.Add(sum(night_vars) <= max_n)

        pair_candidates = self._ojt_pair_candidates()
        ojt_match = {}
        for (target_name, teacher_name, code) in pair_candidates:
            for day in range(1, self.num_days + 1):
                if (target_name, day, code) not in x or (teacher_name, day, code) not in x:
                    continue
                key = (target_name, teacher_name, code, day)
                if key in ojt_match:
                    continue
                var = model.NewBoolVar(f"ojtmatch_{target_name}_{teacher_name}_{code}_{day}")
                model.Add(var <= x[(target_name, day, code)])
                model.Add(var <= x[(teacher_name, day, code)])
                ojt_match[key] = var

        target_names  = {t for t, _te, _c in pair_candidates}
        teacher_names = {te for _t, te, _c in pair_candidates}
        for day in range(1, self.num_days + 1):
            for name in target_names:
                vars_ = [v for (t, _te, _c, d), v in ojt_match.items() if t == name and d == day]
                if vars_:
                    model.Add(sum(vars_) <= 1)
            for name in teacher_names:
                vars_ = [v for (_t, te, _c, d), v in ojt_match.items() if te == name and d == day]
                if vars_:
                    model.Add(sum(vars_) <= 1)

        if "ojt_solo" not in relax:
            for s in self.staff:
                name = s["name"]
                restricted = self._ojt_restricted_codes(s)
                for day in range(1, self.num_days + 1):
                    for c in restricted:
                        if (name, day, c) not in x:
                            continue
                        matches = [
                            v for (t, _te, cc, d), v in ojt_match.items()
                            if t == name and cc == c and d == day
                        ]
                        if matches:
                            model.Add(x[(name, day, c)] <= sum(matches))
                        else:
                            model.Add(x[(name, day, c)] == 0)

        if "ojt_count" not in relax:
            for s in self.staff:
                name = s["name"]
                target_count = s.get("ojt_count", 0)
                if not (s.get("ojt_target") and target_count):
                    continue
                matches_all = [v for (t, _te, _c, _d), v in ojt_match.items() if t == name]
                if matches_all:
                    model.Add(sum(matches_all) >= target_count)
                else:
                    impossible = model.NewBoolVar(f"ojt_impossible_{name}")
                    model.Add(impossible == 1)
                    model.Add(impossible == 0)

        uncounted_names = {
            s["name"] for s in self.staff
            if s.get("ojt_target") and not s.get("ojt_count")
        }
        uncounted_vars = [
            v for (t, _te, _c, _d), v in ojt_match.items() if t in uncounted_names
        ]
        ojt_uncounted_total = sum(uncounted_vars) if uncounted_vars else 0

        balance_terms = []
        for s in self.staff:
            name = s["name"]
            capable_codes = [c for c in ("早1", "遅1", "早4", "遅4") if self._base_capable(s, c)]
            if len(capable_codes) < 2:
                continue
            counts = []
            for c in capable_codes:
                vs = [x[(name, day, c)] for day in range(1, self.num_days + 1) if (name, day, c) in x]
                counts.append(sum(vs) if vs else 0)
            max_c = model.NewIntVar(0, self.num_days, f"maxcount_{name}")
            min_c = model.NewIntVar(0, self.num_days, f"mincount_{name}")
            model.AddMaxEquality(max_c, counts)
            model.AddMinEquality(min_c, counts)
            spread = model.NewIntVar(0, self.num_days, f"spread_{name}")
            model.Add(spread == max_c - min_c)
            balance_terms.append(spread)

        night_capable = [s for s in self.staff if s.get("night_ok")]
        if len(night_capable) >= 2:
            night_counts = []
            for s in night_capable:
                name = s["name"]
                vs = [x[(name, day, self.night_code)] for day in range(1, self.num_days + 1)
                      if (name, day, self.night_code) in x]
                night_counts.append(sum(vs) if vs else 0)
            max_n = model.NewIntVar(0, self.num_days, "maxnights_all")
            min_n = model.NewIntVar(0, self.num_days, "minnights_all")
            model.AddMaxEquality(max_n, night_counts)
            model.AddMinEquality(min_n, night_counts)
            night_spread = model.NewIntVar(0, self.num_days, "nightspread_all")
            model.Add(night_spread == max_n - min_n)
            balance_terms.append(night_spread)

        balance_total = sum(balance_terms) if balance_terms else 0

        leader_gap_vars = []
        leaders = [s for s in self.staff if s.get("leader")]
        daytime_codes_all = self.early_codes + self.late_codes + self.day_codes
        if leaders:
            for day in range(1, self.num_days + 1):
                vars_ = []
                for s in leaders:
                    name = s["name"]
                    for c in daytime_codes_all:
                        if (name, day, c) in x:
                            vars_.append(x[(name, day, c)])
                if not vars_:
                    continue
                gap = model.NewBoolVar(f"leadergap_{day}")
                model.Add(sum(vars_) == 0).OnlyEnforceIf(gap)
                model.Add(sum(vars_) >= 1).OnlyEnforceIf(gap.Not())
                leader_gap_vars.append(gap)
        leader_gap_total = sum(leader_gap_vars) if leader_gap_vars else 0

        meta = {
            "codes_by_person_day": codes_by_person_day,
            "ignored_exception_warnings": ignored_exception_warnings,
            "ojt_match_keys": list(ojt_match.keys()),
            "ojt_uncounted_total": ojt_uncounted_total,
            "balance_total": balance_total,
            "leader_gap_total": leader_gap_total,
        }
        return model, x, ojt_match, meta

    def _diagnose_infeasibility(self, time_limit, seed=1):
        findings = []
        for key, label in DIAG_GROUPS:
            model, _x, _ojt_match, _meta = self._build_model(relax={key})
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = max(time_limit, 60)
            solver.parameters.max_deterministic_time = time_limit
            solver.parameters.num_search_workers = 1
            solver.parameters.random_seed = seed
            status = solver.Solve(model)
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                findings.append(
                    f"⚠ 診断: {label} を緩めると配置可能になります → この規則が衝突の主な原因と見られます"
                )
        if not findings:
            findings.append(
                "⚠ 診断: 規則を1つずつ緩めても解決しません(複数の規則が同時に衝突している可能性が高いです。"
                "人員数やrulesの値をもっと大きく調整してみてください)"
            )
        return findings

    def solve(self, balance_seconds=0, feasibility_time_limit=30, seed=1):
        opt = self._optimize(balance_seconds, feasibility_time_limit, seed)
        if opt is None:
            return self.gen, False
        model, x, ojt_match, meta, solver = opt
        self._populate_result(
            self.gen,
            lambda k: solver.Value(x[k]),
            lambda k: solver.Value(ojt_match[k]),
            meta,
        )
        self.gen.validate()
        return self.gen, not self.gen.hard_errors

    def solve_alternatives(
        self, count=1, balance_seconds=0, feasibility_time_limit=30, seed=1, alternatives_seconds=20
    ):
        opt = self._optimize(balance_seconds, feasibility_time_limit, seed)
        if opt is None:
            return [self.gen], False
        model, x, ojt_match, meta, solver = opt

        if count <= 1:
            self._populate_result(
                self.gen,
                lambda k: solver.Value(x[k]),
                lambda k: solver.Value(ojt_match[k]),
                meta,
            )
            self.gen.validate()
            return [self.gen], not self.gen.hard_errors

        collector = _AlternativeSolutionCollector(x, ojt_match, limit=count)
        model.ClearObjective()
        solver.parameters.enumerate_all_solutions = True
        solver.parameters.max_time_in_seconds = max(alternatives_seconds, 60)
        solver.parameters.max_deterministic_time = alternatives_seconds
        solver.Solve(model, collector)
        solver.parameters.enumerate_all_solutions = False

        gens = []
        for x_vals, ojt_vals in collector.solutions:
            alt_gen = ShiftGenerator(self.config)
            self._populate_result(alt_gen, lambda k: x_vals[k], lambda k: ojt_vals[k], meta)
            alt_gen.validate()
            gens.append(alt_gen)
        if not gens:
            solver.parameters.max_time_in_seconds = 60
            solver.parameters.max_deterministic_time = 30
            solver.Solve(model)
            self._populate_result(
                self.gen,
                lambda k: solver.Value(x[k]),
                lambda k: solver.Value(ojt_match[k]),
                meta,
            )
            self.gen.validate()
            gens = [self.gen]
        return gens, not gens[0].hard_errors

    def _optimize(self, balance_seconds, feasibility_time_limit, seed):
        work_days_budget = self.num_days - self.gen.rules.get("off_days", 0)
        obvious_errors = []
        for s in self.staff:
            target_count = s.get("ojt_count", 0)
            if s.get("ojt_target") and target_count and target_count > work_days_budget:
                obvious_errors.append(
                    f"  ❌ {s['name']}: OJT目標{target_count}回 > 稼働日数{work_days_budget}日"
                    f"(1日に複数回は入れないため、この時点で確実に不可能)"
                )
        if obvious_errors:
            self.gen.hard_errors = [
                "❌ OJT目標(ojt_count)を絶対ルールを守ったまま満たす組み合わせが存在しません "
                "(稼働日数を超えた目標値が設定されています)"
            ] + obvious_errors
            return None

        model, x, ojt_match, meta = self._build_model()

        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.max_time_in_seconds = max(feasibility_time_limit, 60)
        solver.parameters.max_deterministic_time = feasibility_time_limit
        solver.parameters.random_seed = seed

        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            diag = self._diagnose_infeasibility(feasibility_time_limit, seed=seed)
            gen = self.gen
            gen.hard_errors = [
                "❌ 絶対ルールを全て満たす組み合わせが存在しません (CP-SATがINFEASIBLEと証明)"
            ] + diag
            return None

        stage_seconds = max(balance_seconds, 5)

        def _hint_from_solution():
            model.ClearHints()
            for var in x.values():
                model.AddHint(var, solver.Value(var))

        def _pin_and_next(expr):
            if isinstance(expr, int):
                return
            best = solver.Value(expr)
            model.Add(expr == best)

        solver.parameters.max_time_in_seconds = max(stage_seconds, 60)
        solver.parameters.max_deterministic_time = stage_seconds

        if not isinstance(meta["ojt_uncounted_total"], int):
            _hint_from_solution()
            model.Minimize(-meta["ojt_uncounted_total"])
            st = solver.Solve(model)
            if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                _pin_and_next(meta["ojt_uncounted_total"])
                _hint_from_solution()

        model.Minimize(meta["balance_total"])
        st = solver.Solve(model)
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            _pin_and_next(meta["balance_total"])
            _hint_from_solution()

        model.Minimize(meta["leader_gap_total"])
        st = solver.Solve(model)
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            _pin_and_next(meta["leader_gap_total"])
        else:
            model.ClearObjective()
            solver.Solve(model)

        model.ClearObjective()

        _hint_from_solution()

        return model, x, ojt_match, meta, solver

    def _populate_result(self, gen, get_x, get_match, meta):
        match_info = {}
        for key in meta["ojt_match_keys"]:
            target, teacher, code, day = key
            if get_match(key):
                match_info[(target, day)] = ("target", teacher, code)
                match_info[(teacher, day)] = ("teacher", target, code)
                date = gen.date_str(day)
                gen.ojt_map[(date, target)] = code
                gen.ojt_teacher_map[(date, teacher)] = code
                gen.ojt_pairs.append((date, target, teacher, code))
                gen.ojt_partner[(date, target)] = teacher
                gen.ojt_partner[(date, teacher)] = target

        for s in gen.staff:
            name = s["name"]
            for day in range(1, gen.num_days + 1):
                chosen = None
                for c in meta["codes_by_person_day"][(name, day)]:
                    if get_x((name, day, c)):
                        chosen = c
                        break
                role_info = match_info.get((name, day))
                if role_info:
                    role, _partner, code = role_info
                    suffix = "(OJT)" if role == "target" else "(OJT指導)"
                    gen.result[name][day] = f"{code}{suffix}"
                else:
                    gen.result[name][day] = chosen

        gen.assign_warnings.extend(meta["ignored_exception_warnings"])

        for s in gen.staff:
            name = s["name"]
            target_count = s.get("ojt_count", 0)
            if not (s.get("ojt_target") and target_count):
                continue
            achieved = sum(
                1 for d in range(1, gen.num_days + 1)
                if str(gen.result[name].get(d, "")).endswith("(OJT)")
            )
            if achieved < target_count:
                gen.assign_warnings.append(
                    f"⚠ {name}: OJT {target_count}回 目標のうち {achieved}回のみ確保 "
                    f"(内部不整合の可能性: ハード制約を満たしているはずでした)"
                )

def solve_best(config, balance_seconds=0, feasibility_time_limit=30, seed=1):
    solver = ShiftSolver(config)
    return solver.solve(balance_seconds=balance_seconds, feasibility_time_limit=feasibility_time_limit, seed=seed)
