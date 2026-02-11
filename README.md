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

### 2) Configure environment
Create `.env`:
```bash
DATASET_DIR=/absolute/path/to/dataset
DATASET_VERSION=v1
# Default (recommended for local dev, no Docker required)
DATABASE_URL=sqlite:///./agenttest.sqlite
```

### 3) Run the API
```bash
uvicorn api.main:app --reload --port 8000
```

### 4) Run a backtest locally (worker)
```bash
python -m worker.run_backtest --strategy examples/strategies/buy_and_hold.py --dataset $DATASET_DIR
```

### Optional: Postgres mode
Install Postgres driver extras:
```bash
pip install -r requirements-postgres.txt
```
If you want Postgres locally, use Docker compose and set:
```bash
DATABASE_URL=postgresql+psycopg://agenttest:agenttest@localhost:5432/agenttest
```
Then:
```bash
docker compose up -d postgres
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

## API
- `GET /health`
- `POST /strategies` `{ "strategy_path": "/abs/path/to/file.py" }`
- `POST /runs` `{ "strategy_version_id": 1, "params": {} }` or `{ "strategy_path": "/abs/path/to/file.py" }`
- `GET /runs/{run_id}`
- `GET /leaderboard?dataset_version=v1`
- `POST /defaults/promote` `{ "strategy_version_id": 1 }`

## Demo
No-Docker default (SQLite):
```bash
scripts/demo.sh
```

Postgres via Docker:
```bash
USE_DOCKER=1 scripts/demo.sh
```
