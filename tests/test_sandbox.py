"""
Tests for agenttest strategy sandbox and API.

Run with: python -m pytest tests/ -v
"""

import os
import tempfile

import pytest

# Import local modules
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker.sandbox import run_sandboxed, run_unsafe, run_strategy


class TestSandbox:
    """Test sandbox execution environment."""

    def test_sandboxed_simple_strategy(self):
        """Test running a simple strategy in sandbox."""
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if p[0] != 0 else 1.0
    return (p / p0).tolist()
"""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        result = run_sandboxed(code, prices, {})
        assert result == [1.0, 1.01, 1.02, 1.03, 1.04]

    def test_sandboxed_with_params(self):
        """Test running a strategy with parameters."""
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    multiplier = params.get("multiplier", 1.0)
    p0 = p[0] if p[0] != 0 else 1.0
    return ((p / p0) * multiplier).tolist()
"""
        prices = [100.0, 101.0, 102.0]
        result = run_sandboxed(code, prices, {"multiplier": 2.0})
        assert result == [2.0, 2.02, 2.04]

    def test_sandboxed_timeout(self):
        """Test that infinite loops are caught by timeout."""
        code = """
def simulate(prices, params):
    while True:
        pass
"""
        prices = [100.0, 101.0, 102.0]
        with pytest.raises(TimeoutError):
            run_sandboxed(code, prices, {}, timeout_seconds=1)

    def test_sandbox_blocks_network(self):
        """Test that network access is blocked."""
        code = """
import os
# This should be empty in sandbox
assert os.environ.get("HTTP_PROXY") == ""
assert os.environ.get("HTTPS_PROXY") == ""

def simulate(prices, params):
    return [1.0] * len(prices)
"""
        prices = [100.0, 101.0]
        result = run_sandboxed(code, prices, {})
        assert result == [1.0, 1.0]

    def test_sandbox_blocks_file_io(self):
        """Test that file I/O is blocked."""
        code = """
def simulate(prices, params):
    # open() should be None in sandbox
    assert open is None
    return [1.0] * len(prices)
"""
        prices = [100.0, 101.0]
        result = run_sandboxed(code, prices, {})
        assert result == [1.0, 1.0]

    def test_unsafe_runs_directly(self):
        """Test that run_unsafe bypasses sandbox."""
        code = """
import numpy as np

def simulate(prices, params):
    return (np.array(prices) / prices[0]).tolist()
"""
        prices = [100.0, 101.0, 102.0]
        result = run_unsafe(code, prices, {})
        assert result == [1.0, 1.01, 1.02]

    def test_run_strategy_selects_sandbox(self):
        """Test that run_strategy uses sandbox by default."""
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    return (p / p[0]).tolist()
"""
        prices = [100.0, 101.0]
        result = run_strategy(code, prices, {}, trusted=False)
        assert result == [1.0, 1.01]

    def test_run_strategy_trusted_mode(self):
        """Test that run_strategy skips sandbox when trusted=True."""
        code = """
def simulate(prices, params):
    return [1.0] * len(prices)
"""
        prices = [100.0, 101.0]
        result = run_strategy(code, prices, {}, trusted=True)
        assert result == [1.0, 1.0]


class TestStrategyInterface:
    """Test that strategies follow the interface contract."""

    def test_empty_prices_returns_one(self):
        """Empty prices should return [1.0]."""
        code = """
import numpy as np

def simulate(prices, params):
    if not prices:
        return [1.0]
    p = np.asarray(prices, dtype=float)
    return (p / p[0]).tolist()
"""
        result = run_sandboxed(code, [], {})
        assert result == [1.0]

    def test_zero_prices_handled(self):
        """Zero prices should be handled gracefully."""
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    # Handle all zeros - return [1.0] since no trades possible
    if np.all(p == 0):
        return [1.0] * len(p)
    p0 = p[0] if p[0] != 0 else 1.0
    return (p / p0).tolist()
"""
        result = run_sandboxed(code, [0.0, 0.0, 0.0], {})
        assert result == [1.0, 1.0, 1.0]

    def test_return_length_matches_input(self):
        """Return length should match input length."""
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    return (p / p[0]).tolist()
"""
        prices = [100.0] * 100
        result = run_sandboxed(code, prices, {})
        assert len(result) == 100

    def test_first_value_is_one(self):
        """First equity value should always be 1.0."""
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    return (p / p[0]).tolist()
"""
        prices = [100.0, 101.0, 102.0]
        result = run_sandboxed(code, prices, {})
        assert result[0] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
