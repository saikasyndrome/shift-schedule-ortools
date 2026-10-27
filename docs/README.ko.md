# shift-schedule-ortools

*다른 언어: [English](../README.md), [日本語](README.ja.md)*

YAML로 **규칙 값**을 넣고 **OR-Tools CP-SAT**로 근무표를 만든 뒤 Excel로 출력합니다.

- 인원·`off_days`·예외·OJT 횟수 등은 YAML로 바꿈 → [config.md](config.md)
- 시프트 코드(`早1`/`遅1`/`早4`/`遅4`/`夜勤`/`明け`/`休み`/`有給`/`日勤`)와 층 라벨(`floor_a`/`floor_b` 등)은 코드에 고정 (집계·밸런스·범례 등)
- 엔진 흐름 → [architecture.md](architecture.md)

한 줄로: **규칙은 설정화, 시프트 체계는 이 형태로 고정.**

**버전·문제/해결·진단 개선 로드맵:** [CHANGELOG.md](CHANGELOG.md) (현재 **0.2.0**).

## 구조

```text
config/sample.yaml
shift_schedule/   # generator · solver · CLI
tests/
docs/             # CHANGELOG · config · architecture
```

## 빠른 시작

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m shift_schedule config/sample.yaml
python tests/test_solver.py
```
