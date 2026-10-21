# shift-schedule-ortools

*他の言語: [English](../README.md), [한국어](README.ko.md)*

YAML ルールと **OR-Tools CP-SAT** でシフト表を作り、Excel に出力します。

- 設定フィールド: [config.md](config.md)
- 構成/エンジン: [architecture.md](architecture.md)

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
