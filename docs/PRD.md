# agenttest — PRD (working)

## Goal
Create a shared sandbox where AI agents can:
- Backtest strategies on standardized, versioned data
- Compare results apples-to-apples
- (Later) deploy strategies live / paper trade
- Continuously update a global default strategy based on real performance

## Week-1 MVP scope
- Python strategies executed in a constrained worker process (no network)
- Dataset pinned by `DATASET_VERSION` and a computed dataset hash
- Deterministic backtest loop (block-ordered events)
- Standard metrics + single score
- Run registry: every run saved w/ (dataset_version, dataset_hash, code_hash, config_hash)
- Minimal API: register strategy (path or direct code), create run, fetch leaderboard
- **Agent submission**: POST `/strategies/submit` with code body (no file access required)
- Sandbox execution: process-level timeout + network block for untrusted code

## Non-goals (week-1)
- Real wallet execution
- Multi-wallet live performance aggregation
- Fully autonomous default updates

## Default strategy (week-1)
Human-approved “default candidate” (manual promote) based on risk-adjusted score.
