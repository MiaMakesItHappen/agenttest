"""
Strategy Interface Contract & Template for agenttest

A valid strategy must:
1. Define a `simulate(prices, params) -> equity_curve` function
2. Use only numpy and standard library (no network, no file I/O except debug mode)
3. Return a 1D array/sequence of equity values (starting at 1.0)
"""

from __future__ import annotations

from typing import Any, Sequence


def simulate(prices: Sequence[float], params: dict[str, Any]) -> list[float]:
    """
    Run a backtest simulation.

    Args:
        prices: Array of price observations (e.g., daily close prices)
        params: Strategy hyperparameters (e.g., {"threshold": 0.02})

    Returns:
        Equity curve as a list of floats, starting at 1.0
    """
    # Convert to list if it's a pandas Series or numpy array
    if hasattr(prices, 'tolist'):
        prices_list = prices.tolist()
    else:
        prices_list = list(prices)

    # Example: buy and hold
    if not prices_list:
        return [1.0]

    p0 = float(prices_list[0])
    if p0 == 0:
        p0 = 1.0

    equity = [float(p) / p0 for p in prices_list]
    return equity


# Optional: Strategy metadata (used by API for display)
METADATA = {
    "name": "Strategy Template",
    "description": "A template strategy with the required interface",
    "version": "1.0.0",
    "author": "agent",
}
