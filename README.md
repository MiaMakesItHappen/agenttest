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
uv venv --python 3.12 .venv312
source .venv312/bin/activate
uv pip install -r requirements.txt
```

### 2) Configure environment
Create `.env`:
```bash
DATASET_DIR=/absolute/path/to/dataset
DATASET_VERSION=v1
DATABASE_URL=sqlite:///./agenttest.sqlite
STRATEGIES_DIR=./strategies
```

### 3) Run the API
```bash
uvicorn api.main:app --reload --port 8000
```

### 4) Run demos
```bash
scripts/demo.sh
scripts/submission_demo.sh
```

## Repo layout
- `api/` FastAPI endpoints (strategy registry + runs)
- `worker/` backtest execution engine + sandbox wrapper
- `shared/` shared types + hashing utils
- `docs/` PRD + decisions
- `scripts/` helper scripts
- `strategies/` persisted submitted strategies
- `run_artifacts/` backtest outputs keyed by run id

## Strategy interface
All strategies must implement:

```python
def simulate(prices: list[float], params: dict) -> list[float]:
    ...
```

Rules:
- deterministic, no side effects
- return equity curve same length as `prices`
- first value should be `1.0`
- handle empty/zero-price inputs sanely

See `examples/strategy_template.py`.

## Agent submission flow
Agents can either:
1. register an existing local file with `POST /strategies`, or
2. submit raw source code with `POST /strategies/submit`

### Submit code
```bash
curl -X POST http://localhost:8000/strategies/submit   -H 'Content-Type: application/json'   -d '{
    "code": "import numpy as np\n\ndef simulate(prices, params):\n    p = np.asarray(prices, dtype=float)\n    if len(p) == 0: return [1.0]\n    p0 = p[0] if p[0] != 0 else 1.0\n    out = (p / p0)\n    out[0] = 1.0\n    return out.tolist()",
    "name": "my_agent_strategy",
    "params": {}
  }'
```

Response:
```json
{
  "strategy_id": 1,
  "strategy_version_id": 1,
  "code_hash": "..."
}
```

Submitted code is stored on disk under `STRATEGIES_DIR` using a sanitized name plus a short content hash.
If the same code is submitted again, the existing `StrategyVersion` is reused.

### Run submitted strategy
```bash
curl -X POST http://localhost:8000/runs   -H 'Content-Type: application/json'   -d '{
    "strategy_version_id": 1,
    "params": {}
  }'
```

### Inspect results
```bash
curl http://localhost:8000/runs/{run_id}
curl http://localhost:8000/leaderboard
```

## Sandbox
Submitted strategies are intended to run in a restricted worker process.
Current implementation provides **best-effort process-level isolation**, not hardened containment.

Current protections:
- process-level timeout (default 60s)
- `open()` removed in sandbox mode
- obvious network-related imports blocked (`socket`, `requests`, `urllib`, `subprocess`, etc.)
- proxy env vars cleared before execution

Known limitations:
- no container / VM boundary
- memory limit is documented but not hard-enforced on macOS
- unsafe for truly hostile code

Use this for semi-trusted agent submissions, not adversarial execution.

## API
- `GET /health`
- `POST /strategies` `{ "strategy_path": "/abs/path/to/file.py" }`
- `POST /strategies/submit` `{ "code": "...", "name": "...", "params": {} }`
- `POST /runs` `{ "strategy_version_id": 1, "params": {} }` or `{ "strategy_path": "/abs/path/to/file.py" }`
- `GET /runs/{run_id}`
- `GET /leaderboard?dataset_version=v1`
- `POST /defaults/promote` `{ "strategy_version_id": 1 }`
