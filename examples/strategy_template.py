"""
Strategy Interface Contract for agenttest

This module defines the required interface for all trading strategies
submitted to the agenttest platform.

REQUIRED FUNCTION
-----------------
def simulate(prices: list[float], params: dict[str, Any]) -> list[float]:
    '''
    Simulate a trading strategy on historical price data.

    Args:
        prices: List of price data points (e.g., closing prices)
        params: Configuration parameters for the strategy
                (can be tuned via the params field in run requests)

    Returns:
        List of equity values (starting at 1.0, representing
        portfolio value over time relative to initial capital)

    Examples:
        >>> prices = [100, 101, 102, 103, 104]
        >>> simulate(prices, {})
        [1.0, 1.01, 1.02, 1.03, 1.04]  # Buy and hold

        >>> simulate(prices, {"threshold": 0.02})
        [...]  # Custom strategy with threshold parameter
    '''

REQUIREMENTS
------------
1. Pure function: The simulate() function must be deterministic and
   have no side effects (no file I/O, network calls, or global state).

2. Handle edge cases:
   - Empty prices list: Return [1.0] (no trades possible)
   - Zero prices: Return list of 1.0s (can't trade)
   - Invalid params: Use defaults or raise ValueError

3. Performance:
   - Expected runtime < 10 seconds for 10,000+ price points
   - Avoid O(n²) operations on large datasets

4. Return format:
   - Must return list of floats with same length as input prices
   - First value should be 1.0 (starting equity)
   - Values represent cumulative portfolio value

OPTIONAL COMPONENTS
-------------------
You may include these in your strategy module:

1. validate_params(params: dict) -> dict:
   '''Validate and sanitize parameters. Returns corrected params.'''
   - Used to provide defaults and bounds checking

2. default_params() -> dict:
   '''Return default parameters for this strategy.'''
   - Example: {"threshold": 0.01, "window": 20}

3. strategy_name() -> str:
   '''Return a human-readable name for display purposes.'''

METRICS COMPUTED
----------------
The platform automatically computes these metrics from the returned equity curve:

- total_return: (final_equity - 1.0) * 100
- cagr: Compound Annual Growth Rate
- max_drawdown: Maximum peak-to-trough decline
- volatility: Standard deviation of returns
- sharpe: Risk-adjusted return (return / volatility)
- capital_efficiency: How effectively capital was utilized
- score: Platform-defined scoring (combines above metrics)

SANDBOX LIMITS
--------------
Submitted strategies run in a restricted environment:
- Maximum runtime: 60 seconds
- No network access
- No file I/O (read or write)
- No subprocess spawning
- Memory limit: 256 MB

Violations will result in strategy rejection or run failure.

VERSIONING
----------
Strategies are stored with:
- Unique code_hash (SHA-256 of file contents)
- StrategyVersion record in database
- Optional: written to strategies/ directory for persistence

The same code hash will reuse existing StrategyVersion records.
"""

from typing import Any


def simulate(prices: list[float], params: dict[str, Any]) -> list[float]:
    """
    Simulate a trading strategy on historical price data.

    Args:
        prices: List of price data points
        params: Strategy parameters for tuning

    Returns:
        List of equity values starting at 1.0
    """
    import numpy as np

    if not prices:
        return [1.0]

    prices = np.asarray(prices, dtype=float)
    p0 = prices[0] if prices[0] != 0 else 1.0
    equity = prices / p0
    return equity.tolist()


def default_params() -> dict[str, Any]:
    """Return default parameters for this strategy."""
    return {}


def validate_params(params: dict[str, Any]) -> dict[str, Any]:
    """Validate and return sanitized parameters."""
    defaults = default_params()
    validated = defaults.copy()
    for key, expected_type in defaults.items():
        if key in params and isinstance(params[key], type(expected_type)):
            validated[key] = params[key]
    return validated
