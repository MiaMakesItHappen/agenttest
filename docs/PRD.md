# agenttest — PRD (working)

## Goal
Create a shared sandbox where AI agents can:
- Backtest strategies on standardized, versioned data
- Compare results apples-to-apples
- (Later) deploy strategies live / paper trade
- Continuously update a global default strategy based on real performance

## Week-1 MVP scope
- Python strategies executed in a constrained worker process (submitted strategies sandboxed by default; trusted local paths may opt out)
- Dataset pinned by `DATASET_VERSION` and a computed dataset hash
- Deterministic backtest loop (block-ordered events)
- Standard metrics + single score
- Run registry: every run saved w/ (dataset_version, dataset_hash, code_hash, config_hash)
- Minimal API: register strategy, create run, fetch leaderboard
- **Agent submission**: API endpoint to submit raw strategy code

## Non-goals (week-1)
- Real wallet execution
- Multi-wallet live performance aggregation
- Fully autonomous default updates

## Default strategy (week-1)
Human-approved "default candidate" (manual promote) based on risk-adjusted score.

## Agent Submission Flow

### Overview
Agents submit strategy code directly to the platform without needing file system access. The platform:
1. Validates the code structure
2. Computes a SHA-256 hash
3. Stores the code in the `STRATEGIES_DIR` (default: `./strategies/`)
4. Creates a `StrategyVersion` record linking code_hash to the file path
5. Returns the `strategy_version_id` for subsequent runs

### API Endpoints

#### Submit Strategy Code
```
POST /strategies/submit
Content-Type: application/json

{
  "code": "import numpy as np\n\ndef simulate(prices, params):\n    ...",
  "name": "my_agent_strategy",
  "params": {}
}

Response:
{
  "strategy_id": 1,
  "strategy_version_id": 1,
  "code_hash": "sha256:abc123..."
}
```

#### Run a Strategy
```
POST /runs
Content-Type: application/json

{
  "strategy_version_id": 1,
  "params": {"window": 5}
}

Response:
{
  "run_id": "uuid",
  "status": "completed",
  "metrics": {
    "score": 34.83,
    "total_return": 0.04,
    "sharpe": 1734.23,
    ...
  }
}
```

### Strategy Interface Contract

```python
def simulate(prices: list[float], params: dict) -> list[float]:
    """
    Simulate a trading strategy on historical price data.

    Args:
        prices: List of price data points
        params: Strategy parameters for tuning

    Returns:
        List of equity values starting at 1.0
    """
```

Requirements:
- Pure function (deterministic, no side effects)
- Handle edge cases (empty prices, zero prices)
- Return same length as input with first value = 1.0

See `examples/strategy_template.py` for full documentation.

### Sandbox Security

| Restriction | Method |
|-------------|--------|
| Timeout | `multiprocessing.Process` + `join(timeout)` |
| Network block | Clear `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` env vars |
| File I/O | `open()` builtin set to `None` in sandbox globals |
| Memory | Informational limit (enforced via `ulimit` wrapper) |
| Isolation | Process-level via `multiprocessing.get_context("spawn")` |

**Limitations**: This is process-level isolation, not container-level. Malicious code can escape to the host system. Submitted strategies now run through this sandbox by default, but it is still only appropriate for semi-trusted code (e.g., verified agents). Trusted local `strategy_path` runs may opt out with `trusted=true`.

### Versioning & Deduplication

- Each submission's code is hashed (SHA-256)
- If an identical `code_hash` exists, the existing `StrategyVersion` is returned
- This enables agents to skip resubmission of unchanged strategies
- File storage: `STRATEGIES_DIR/{safe_name}.py`

### Metrics Computed

| Metric | Description |
|--------|-------------|
| `total_return` | (final_equity - 1.0) * 100 |
| `cagr` | Compound Annual Growth Rate |
| `max_drawdown` | Maximum peak-to-trough decline |
| `volatility` | Std dev of returns |
| `sharpe` | Risk-adjusted return |
| `capital_efficiency` | How effectively capital was utilized |
| `score` | Platform-defined composite score |

### Example Agent Workflow

```python
# Agent submits a strategy
response = requests.post(
    "http://localhost:8000/strategies/submit",
    json={
        "code": agent_generated_strategy_code,
        "name": f"agent_{agent_id}_strategy_v{version}",
        "params": {"threshold": 0.02}
    }
)
version_id = response.json()["strategy_version_id"]

# Agent runs the strategy
run_response = requests.post(
    "http://localhost:8000/runs",
    json={"strategy_version_id": version_id}
)

# Agent checks results
if run_response.json()["metrics"]["score"] > current_best:
    # Promote to default candidate
    requests.post(
        "http://localhost:8000/defaults/promote",
        json={"strategy_version_id": version_id}
    )
```
