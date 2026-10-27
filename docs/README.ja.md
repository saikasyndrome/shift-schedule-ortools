# shift-schedule-ortools

*他の言語: [English](../README.md), [한국어](README.ko.md)*

YAML で **ルール値** を入れ、**OR-Tools CP-SAT** でシフト表を作り Excel に出力します。

- 人員・`off_days`・例外・OJT 回数などは YAML で変更 → [config.md](config.md)
- シフトコード（`早1`/`遅1`/`早4`/`遅4`/`夜勤`/`明け`/`休み`/`有給`/`日勤`）と病棟ラベル（`floor_a`/`floor_b` など）はコード側に固定（集計・バランス・凡例など）
- エンジンの流れ → [architecture.md](architecture.md)

一言で: **ルールは設定化、シフト体系はこの形で固定。**

**バージョン・問題→解決・診断ロードマップ:** [CHANGELOG.md](CHANGELOG.md)（現在 **0.2.0**）。

## 構成

```text
config/sample.yaml
shift_schedule/   # generator · solver · CLI
tests/
docs/
```

## クイックスタート

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m shift_schedule config/sample.yaml
python tests/test_solver.py
```
