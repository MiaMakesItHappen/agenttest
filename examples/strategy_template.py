"""
Strategy Interface Contract for agenttest

Every strategy must expose:
    simulate(prices: list[float], params: dict[str, Any]) -> list[float]

Contract:
- deterministic and side-effect free
- returns an equity curve with the same length as prices
- first value should be 1.0 when prices are present
- handles empty/zero-price input safely

Optional helpers:
- default_params() -> dict[str, Any]
- validate_params(params: dict[str, Any]) -> dict[str, Any]
- strategy_name() -> str

Sandbox notes:
- submitted code is executed in a separate process
- timeout defaults to 60s
- obvious network-related imports are blocked
- open() is unavailable in sandbox mode
- this is not a secure container and should be treated as best-effort only
"""

from typing import Any

import numpy as np


def simulate(prices: list[float], params: dict[str, Any]) -> list[float]:
    if not prices:
        return [1.0]

    p = np.asarray(prices, dtype=float)
    if len(p) == 0:
        return [1.0]
    if np.all(p == 0):
        return [1.0] * len(p)

    p0 = p[0] if p[0] != 0 else 1.0
    equity = p / p0
    if len(equity) > 0:
        equity[0] = 1.0
    return equity.tolist()


def default_params() -> dict[str, Any]:
    return {}


def validate_params(params: dict[str, Any]) -> dict[str, Any]:
    return dict(params or {})


def strategy_name() -> str:
    return "strategy_template"
