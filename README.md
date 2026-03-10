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
# Optional: directory for submitted strategies (default: strategies/)
STRATEGIES_DIR=./strategies
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
- `strategies/` directory for submitted agent strategies

## Notes
- Week-1 goal is reproducibility: **dataset_version + code_hash + config_hash**.
- Dataset should not be committed to git unless explicitly using Git LFS.

## Strategy Interface

All strategies must implement a `simulate(prices, params)` function:

```python
import numpy as np

def simulate(prices: list[float], params: dict) -> list[float]:
    """
    Args:
        prices: List of price data points
        params: Strategy parameters for tuning

    Returns:
        List of equity values starting at 1.0
    """
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if p[0] != 0 else 1.0
    equity = p / p0
    return equity.tolist()
```

See `examples/strategy_template.py` for the full contract and documentation.

## Agent Submission Flow

Agents can submit strategies directly via API:

### 1. Submit strategy code
```bash
curl -X POST http://localhost:8000/strategies/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "code": "import numpy as np\n\ndef simulate(prices, params):\n    p = np.asarray(prices, dtype=float)\n    return (p / p[0]).tolist() if p[0] != 0 else [1.0] * len(p)",
    "name": "my_agent_strategy",
    "params": {}
  }'
```

Response:
```json
{
  "strategy_id": 1,
  "strategy_version_id": 1,
  "code_hash": "abc123..."
}
```

### 2. Run the strategy
```bash
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "strategy_version_id": 1,
    "params": {}
  }'
```

### 3. Check results
```bash
curl http://localhost:8000/runs/{run_id}
curl http://localhost:8000/leaderboard
```

## Sandbox

Submitted strategies run in a restricted environment:

- **Timeout**: 60 seconds maximum execution time
- **Memory**: 256 MB limit
- **Network**: Blocked (HTTP_PROXY, HTTPS_PROXY cleared)
- **File I/O**: Blocked in sandbox mode
- **Isolation**: Process-level via multiprocessing

Submitted strategies (`strategy_version_id`) always run inside the process sandbox. Trusted local files can still use `strategy_path` with `trusted=true` to skip sandbox for local development.

## API
- `GET /health`
- `POST /strategies` `{ "strategy_path": "/abs/path/to/file.py" }`
- `POST /strategies/submit` `{ "code": "...", "name": "...", "params": {} }`
- `POST /runs` `{ "strategy_version_id": 1, "params": {} }` (sandboxed submission) or `{ "strategy_path": "/abs/path/to/file.py", "trusted": true }` (trusted local file)
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

Agent submission demo:
```bash
scripts/submission_demo.sh
```
