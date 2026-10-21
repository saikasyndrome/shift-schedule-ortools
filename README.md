# shift-schedule-ortools

*Read this in other languages: [한국어](docs/README.ko.md), [日本語](docs/README.ja.md)*

Constraint-based **staff shift scheduler** in Python.

- Rules and roster in YAML → see [docs/config.md](docs/config.md)
- **Google OR-Tools CP-SAT** for hard constraints + soft goals → [docs/architecture.md](docs/architecture.md)
- Excel export

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
