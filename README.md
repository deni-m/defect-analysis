# QA Bugs Analytics (Starter)

## Quick start
```bash
# 1) Create venv & install
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

# 2) Run on sample data (produces output/run_YYYYMMDD_HHMM/report.html)
qa-bugs run   --config configs/example.config.yml   --input data/sample_bugs.csv   --since 2025-09-01 --until 2025-09-30   --metrics defect_age,age_by_priority   --llm off
```

Open the generated `report.html` in a browser.
