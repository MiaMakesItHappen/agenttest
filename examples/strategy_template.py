"""
Strategy Template for agenttest

All strategies MUST implement a simulate() function with this exact signature:

    def simulate(prices: list[float], params: dict) -> np.ndarray:
        ...

Arguments:
- prices: list of float prices (chronologically ordered)
- params: dict of configuration parameters (optional, can be empty)

Returns:
- np.ndarray of equity curve (same length as prices)

Requirements:
- Function must be named 'simulate'
- Must return a numpy array of floats
- Array length must match len(prices)
- No network access (sandbox will block external connections)
- Execution timeout: 60 seconds (configurable)

Example:
"""

import numpy as np


def simulate(prices: list[float], params: dict) -> np.ndarray:
    """
    Example: Buy and hold strategy.
    
    Normalizes prices to equity curve starting at 1.0.
    """
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if len(p) > 0 and p[0] != 0 else 1.0
    equity = p / p0
    return equity
