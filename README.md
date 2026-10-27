# shift-schedule-ortools

*Read this in other languages: [한국어](docs/README.ko.md), [日本語](docs/README.ja.md)*

Constraint-based **staff shift scheduler** in Python.

- **Rule values** (roster, `off_days`, caps, exceptions, OJT counts, …) live in YAML → [docs/config.md](docs/config.md)
- **Shift scheme** (codes `早1`/`遅1`/`早4`/`遅4`/`夜勤`/`明け`/`休み`/`有給`/`日勤` and ward labels like `floor_a`/`floor_b`) is **fixed in code** (summary, balance targets, daytime checks, Excel legend, …)
- **Google OR-Tools CP-SAT** for hard constraints + soft goals → [docs/architecture.md](docs/architecture.md)
- Excel export

In short: rules are configurable; the shift vocabulary is this domain shape.

**Versions / problems & fixes / diagnosis roadmap:** [docs/CHANGELOG.md](docs/CHANGELOG.md) (current **0.2.0**).

## Layout

```text
.
├── config/sample.yaml       # sample input
├── shift_schedule/
│   ├── generator.py         # parse, heuristic, validate, Excel
│   ├── solver.py            # CP-SAT engine
│   └── __main__.py          # CLI
├── tests/test_solver.py
└── docs/
    ├── CHANGELOG.md         # versioned problems → fixes → improvements
    ├── config.md
    └── architecture.md
```

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m shift_schedule config/sample.yaml
python tests/test_solver.py
```

## Topics

`python` · `ortools` · `cp-sat` · `scheduling` · `yaml` · `excel`
