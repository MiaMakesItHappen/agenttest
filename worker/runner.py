from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from shared.hashing import sha256_bytes, sha256_json
from shared.types import RunResult


def hash_file(path: str) -> str:
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def hash_dataset_dir(dataset_dir: str) -> str:
    """MVP: hash file names + sizes + mtimes. Replace with content-hash when stable."""
    h = []
    for root, _, files in os.walk(dataset_dir):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            st = os.stat(p)
            rel = os.path.relpath(p, dataset_dir)
            h.append(f"{rel}:{st.st_size}:{int(st.st_mtime)}")
    return sha256_bytes("\n".join(h).encode("utf-8"))


def load_price_series(dataset_dir: str) -> pd.Series:
    """Expect a simple CSV: prices.csv with columns: ts, price

    This is a placeholder until we map your real dataset schema.
    """
    path = os.path.join(dataset_dir, "prices.csv")
    df = pd.read_csv(path)
    df = df.sort_values(df.columns[0])
    return pd.Series(df[df.columns[1]].values)


def run_backtest(
    strategy_path: str,
    dataset_dir: str,
    dataset_version: str,
    params: Dict[str, Any],
    run_id: str | None = None,
) -> RunResult:
    run_id = run_id or str(uuid.uuid4())
    started = time.time()

    dataset_hash = hash_dataset_dir(dataset_dir)
    code_hash = hash_file(strategy_path)
    config_hash = sha256_json({"params": params, "dataset_version": dataset_version})

    # Load strategy
    strategy_globals: Dict[str, Any] = {}
    with open(strategy_path, "r", encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, strategy_path, "exec"), strategy_globals)

    if "simulate" not in strategy_globals:
        raise ValueError("Strategy must define simulate(prices, params) -> equity_curve")

    prices = load_price_series(dataset_dir)
    equity = strategy_globals["simulate"](prices=prices, params=params)
    equity = pd.Series(equity, dtype=float)

    # Metrics (very MVP)
    steps_per_year = float(params.get("steps_per_year", 365))
    n_steps = max(len(equity) - 1, 0)

    ret = (equity.iloc[-1] / equity.iloc[0]) - 1.0 if len(equity) > 1 else 0.0
    max_dd = ((equity / equity.cummax()) - 1.0).min() if len(equity) > 0 else 0.0

    if n_steps > 0 and equity.iloc[0] != 0:
        cagr = (equity.iloc[-1] / equity.iloc[0]) ** (steps_per_year / n_steps) - 1.0
    else:
        cagr = 0.0

    returns = equity.pct_change().dropna()
    if len(returns) > 0:
        vol = float(returns.std(ddof=0) * np.sqrt(steps_per_year))
        mean_ann = float(returns.mean() * steps_per_year)
        sharpe = 0.0 if vol == 0 else float(mean_ann / vol)
    else:
        vol = 0.0
        sharpe = 0.0

    liquidation_events = 0
    capital_efficiency = 0.0
    score = float(cagr) - 0.7 * abs(float(max_dd))

    metrics = {
        "total_return": float(ret),
        "cagr": float(cagr),
        "max_drawdown": float(max_dd),
        "volatility": float(vol),
        "sharpe": float(sharpe),
        "liquidation_events": liquidation_events,
        "capital_efficiency": float(capital_efficiency),
        "score": float(score),
        "runtime_s": float(time.time() - started),
    }

    artifacts_dir = os.path.join("run_artifacts", run_id)
    os.makedirs(artifacts_dir, exist_ok=True)
    pd.DataFrame({"step": list(range(len(equity))), "equity": equity.values}).to_csv(
        os.path.join(artifacts_dir, "equity.csv"), index=False
    )

    return RunResult(
        run_id=run_id,
        dataset_version=dataset_version,
        dataset_hash=dataset_hash,
        code_hash=code_hash,
        config_hash=config_hash,
        metrics=metrics,
        artifacts_dir=artifacts_dir,
    )
