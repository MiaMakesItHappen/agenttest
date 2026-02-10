# agenttest

1-week MVP scaffold for a **strategy sandbox** with **Python strategies**.

## What this repo will become
- **API** to register strategies + trigger runs
- **Worker** to execute deterministic backtests over a pinned dataset version
- **Run registry** + standardized metrics
- (Later) live/paper trading + default-strategy updater

## Quick start (dev)
### 1) Create a virtualenv
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure dataset path
Create `.env`:
```bash
DATASET_DIR=/absolute/path/to/dataset
DATASET_VERSION=v1
```

### 3) Run the API
```bash
uvicorn api.main:app --reload --port 8000
```

### 4) Run a backtest locally (worker)
```bash
python -m worker.run_backtest --strategy examples/strategies/buy_and_hold.py --dataset $DATASET_DIR
```

## Repo layout
- `api/` FastAPI endpoints (strategy registry + runs)
- `worker/` backtest execution engine + sandbox wrapper
- `shared/` shared types + hashing utils
- `docs/` PRD + decisions
- `scripts/` helper scripts

## Notes
- Week-1 goal is reproducibility: **dataset_version + code_hash + config_hash**.
- Dataset should not be committed to git unless explicitly using Git LFS.
