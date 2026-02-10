from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict

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


def run_backtest(strategy_path: str, dataset_dir: str, dataset_version: str, params: Dict[str, Any]) -> RunResult:
    run_id = str(uuid.uuid4())
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
    equity = pd.Series(equity)

    # Metrics (very MVP)
    ret = (equity.iloc[-1] / equity.iloc[0]) - 1.0
    max_dd = ((equity / equity.cummax()) - 1.0).min()

    metrics = {
        "total_return": float(ret),
        "max_drawdown": float(max_dd),
        "liquidation_events": 0,
        "score": float(ret) - 0.7 * abs(float(max_dd)),
        "runtime_s": float(time.time() - started),
    }

    return RunResult(
        run_id=run_id,
        dataset_version=dataset_version,
        dataset_hash=dataset_hash,
        code_hash=code_hash,
        config_hash=config_hash,
        metrics=metrics,
        artifacts_dir=None,
    )
