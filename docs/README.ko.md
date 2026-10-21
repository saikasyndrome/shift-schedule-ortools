# shift-schedule-ortools

*다른 언어: [English](../README.md), [日本語](README.ja.md)*

YAML 규칙 + **OR-Tools CP-SAT**로 근무표를 만들고 Excel로 출력합니다.

- 설정 필드: [config.md](config.md)
- 구조/엔진: [architecture.md](architecture.md)

## 구조

```text
config/sample.yaml
shift_schedule/   # generator · solver · CLI
tests/
docs/
```

## 빠른 시작

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m shift_schedule config/sample.yaml
python tests/test_solver.py
```
