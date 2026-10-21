"""CLI: python -m shift_schedule [config.yaml]"""
import sys

from shift_schedule.generator import load_config, generate_best, ExcelExporter


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    old_argv = sys.argv
    sys.argv = [old_argv[0], *argv]
    try:
        _run()
    finally:
        sys.argv = old_argv


def _run():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/sample.yaml"
    config      = load_config(config_path)

    year  = config["schedule"]["year"]
    month = config["schedule"]["month"]
    ENGINE          = config["schedule"].get("engine", "solver")
    BALANCE_SECONDS = config["schedule"].get("balance_seconds", 0)
    ALTERNATIVES      = config["schedule"].get("alternatives", 1)
    ALTERNATIVES_SECS = config["schedule"].get("alternatives_seconds", 20)

    if ENGINE == "heuristic":
        base_seed    = config["schedule"].get("seed", 1)
        MAX_ATTEMPTS = config["schedule"].get("attempts", 1000)
        DAY_ATTEMPTS = config["schedule"].get("day_attempts", 30)

        print(f"\n🔧 シフト生成開始(heuristic): {year}年{month}月 (seed={base_seed}から最大{MAX_ATTEMPTS}通り探索)")

        try:
            gen, success = generate_best(
                config, base_seed=base_seed, max_attempts=MAX_ATTEMPTS,
                day_attempts=DAY_ATTEMPTS, balance_seconds=BALANCE_SECONDS,
            )
        except ValueError as e:
            print(f"\n❌ 設定エラー: {e}", file=sys.stderr)
            print("Excelファイルは出力されません。config/sample.yaml の rules を見直してください。", file=sys.stderr)
            sys.exit(1)

        if success:
            print(f"ℹ️  seed={base_seed} からの探索で絶対ルール違反なく生成できました")
        else:
            print(
                f"\n❌ seed={base_seed} から最大{MAX_ATTEMPTS}通り(日単位の部分やり直しも含む)を"
                f"試しましたが、絶対ルールを守ったシフトを作成できませんでした "
                f"(最良の結果でも{len(gen.hard_errors)}件の違反):",
                file=sys.stderr,
            )
            for w in gen.hard_errors:
                print(f"  {w}", file=sys.stderr)
            print(
                "\nExcelファイルは出力されません。"
                "config/sample.yaml の人員数・rules(max_consecutive/off_days/"
                "night_required_per_day 等)を見直してください。",
                file=sys.stderr,
            )
            sys.exit(1)

        output_path = f"shift_{year}{month:02d}_seed{base_seed}.xlsx"
        gens = [gen]

    else:
        from shift_schedule.solver import ShiftSolver

        seed = config["schedule"].get("seed", 1)

        if ALTERNATIVES > 1:
            print(
                f"\n🔧 シフト生成開始(solver/CP-SAT): {year}年{month}月 "
                f"(seed={seed}, 別解を最大{ALTERNATIVES}個まで探索)"
            )
        else:
            print(f"\n🔧 シフト生成開始(solver/CP-SAT): {year}年{month}月 (seed={seed})")

        try:
            solver = ShiftSolver(config)
        except ValueError as e:
            print(f"\n❌ 設定エラー: {e}", file=sys.stderr)
            print("Excelファイルは出力されません。config/sample.yaml の rules を見直してください。", file=sys.stderr)
            sys.exit(1)

        if ALTERNATIVES > 1:
            gens, success = solver.solve_alternatives(
                count=ALTERNATIVES, balance_seconds=BALANCE_SECONDS, seed=seed,
                alternatives_seconds=ALTERNATIVES_SECS,
            )
        else:
            gen, success = solver.solve(balance_seconds=BALANCE_SECONDS, seed=seed)
            gens = [gen]

        if success:
            if len(gens) > 1:
                print(f"ℹ️  CP-SATが絶対ルール違反なしの組み合わせを{len(gens)}個見つけました(全て同じ優先順位で最良)")
            else:
                print("ℹ️  CP-SATが絶対ルール違反なしの組み合わせを見つけました")
        else:
            gen = gens[0]
            print(
                "\n❌ 絶対ルールを全て満たす組み合わせが存在しないことをCP-SATが数学的に確認しました:",
                file=sys.stderr,
            )
            for w in gen.hard_errors:
                print(f"  {w}", file=sys.stderr)
            print(
                "\nExcelファイルは出力されません。"
                "config/sample.yaml の人員数・rules(max_consecutive/off_days/"
                "night_required_per_day 等)を見直してください。",
                file=sys.stderr,
            )
            sys.exit(1)

        output_path = f"shift_{year}{month:02d}_solver_seed{seed}.xlsx"

    def _report(gen, output_path):
        exporter = ExcelExporter(gen)
        warnings = exporter.export(output_path)

        print(f"✅ 出力完了: {output_path}")
        print(f"\n📋 サマリー:")
        for row in gen.summary():
            unassigned_str = f" 未配置{row['unassigned']}件" if row["unassigned"] else ""
            ojt_str        = f" OJT{row['ojt']}回"          if row["ojt"]        else ""
            ojt_teach_str  = f" OJT指導{row['ojt_teach']}回" if row["ojt_teach"]  else ""
            def fmt2(v):
                return f"{v:>2}" if isinstance(v, str) else f"{v:2d}"
            def fmt_night(v):
                return f"{v:>2}" if isinstance(v, str) else f"{v:2d}"
            print(f"  {row['name']:6s} 出勤{row['work']:2d}日 "
                  f"早1:{fmt2(row['early1'])} 遅1:{fmt2(row['late1'])} "
                  f"早4:{fmt2(row['early4'])} 遅4:{fmt2(row['late4'])} "
                  f"夜勤{fmt_night(row['nights'])}回 "
                  f"総時間{row['hours']:5.1f}h"
                  f"{ojt_str}{ojt_teach_str}{unassigned_str}")

        if warnings:
            print(f"\n⚠️  警告 ({len(warnings)}件):")
            for w in warnings:
                print(f"  {w}")
        else:
            print("\n✅ ルール違反なし")

    if len(gens) > 1:
        stem, ext = output_path.rsplit(".", 1)
        for i, g in enumerate(gens, start=1):
            print(f"\n=== 別解 {i}/{len(gens)} ===")
            _report(g, f"{stem}_alt{i}.{ext}")
    else:
        _report(gens[0], output_path)


if __name__ == "__main__":
    main()
