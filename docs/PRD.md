# agenttest — PRD (working)

## Goal
Create a shared sandbox where AI agents can:
- Backtest strategies on standardized, versioned data
- Compare results apples-to-apples
- (Later) deploy strategies live / paper trade
- Continuously update a global default strategy based on real performance

## Week-1 MVP scope
- Python strategies executed in a constrained worker process
- Dataset pinned by `DATASET_VERSION` and a computed dataset hash
- Deterministic backtest loop (block-ordered events)
- Standard metrics + single score
- Run registry: every run saved with `(dataset_version, dataset_hash, code_hash, config_hash)`
- Minimal API: register strategy, create run, fetch leaderboard
- Agent submission endpoint for raw strategy code
- Persist submitted strategy source on disk for later replay/debugging

## Non-goals (week-1)
- Real wallet execution
- Multi-wallet live performance aggregation
- Fully autonomous default updates
- Strong hostile-code isolation

## Agent submission flow
1. Agent submits code to `POST /strategies/submit`
2. API validates the presence of `simulate(prices, params)`
3. API computes `code_hash = sha256(code)`
4. If hash already exists, existing `StrategyVersion` is returned
5. Otherwise code is written to `STRATEGIES_DIR/{safe_name}_{short_hash}.py`
6. New `Strategy` + `StrategyVersion` rows are created
7. Agent triggers `POST /runs` using `strategy_version_id`
8. Run artifacts are written under `run_artifacts/{run_id}/`

This keeps the original `strategy_path` registration flow intact for trusted local files.

## Strategy interface contract
Required entrypoint:

```python
def simulate(prices: list[float], params: dict[str, Any]) -> list[float]:
    ...
```

Rules:
- deterministic, no side effects
- output length matches input length
- first equity value should be `1.0` when input is non-empty
- should handle empty lists and zero-price inputs gracefully

Optional helpers:
- `default_params()`
- `validate_params(params)`
- `strategy_name()`

Reference implementation: `examples/strategy_template.py`

## Sandbox design
Current worker isolation is intentionally lightweight:
- separate child process via `multiprocessing.get_context("spawn")`
- parent enforces timeout with `join(timeout=...)`
- obvious network/subprocess imports blocked by custom import gate
- `open()` removed from sandbox builtins
- proxy env vars cleared before execution

### Limitations
This is **not** a secure sandbox.
- no containerization / seccomp / syscall filtering
- memory limits not hard-enforced on macOS
- Python introspection still makes this unsuitable for adversarial code

Practical stance: good enough for an agent playground MVP, not good enough for hostile internet submissions.

## Minimal API surface
- `POST /strategies` for existing local file paths
- `POST /strategies/submit` for source-code submissions
- `POST /runs` for executing a strategy version or path
- `GET /runs/{run_id}` for run details
- `GET /leaderboard` for score ranking
- `POST /defaults/promote` for manual default promotion

## Example workflow
```python
submit = requests.post(
    "http://localhost:8000/strategies/submit",
    json={
        "code": generated_code,
        "name": "agent_alpha",
        "params": {"window": 5},
    },
)
version_id = submit.json()["strategy_version_id"]

run = requests.post(
    "http://localhost:8000/runs",
    json={"strategy_version_id": version_id, "params": {"window": 5}},
)
```
