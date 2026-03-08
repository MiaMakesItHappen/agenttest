"""Tests for agenttest strategy sandbox and API."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker.sandbox import run_sandboxed, run_strategy, run_unsafe


class TestSandbox:
    def test_sandboxed_simple_strategy(self):
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if p[0] != 0 else 1.0
    out = p / p0
    out[0] = 1.0
    return out.tolist()
"""
        result = run_sandboxed(code, [100.0, 101.0, 102.0], {})
        assert result == [1.0, 1.01, 1.02]

    def test_sandboxed_with_params(self):
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    multiplier = params.get("multiplier", 1.0)
    p0 = p[0] if p[0] != 0 else 1.0
    out = (p / p0) * multiplier
    return out.tolist()
"""
        result = run_sandboxed(code, [100.0, 101.0, 102.0], {"multiplier": 2.0})
        assert result == [2.0, 2.02, 2.04]

    def test_sandboxed_timeout(self):
        code = """
def simulate(prices, params):
    while True:
        pass
"""
        with pytest.raises(TimeoutError):
            run_sandboxed(code, [100.0, 101.0], {}, timeout_seconds=1)

    def test_sandbox_blocks_os_import(self):
        code = """
import os

def simulate(prices, params):
    return [1.0] * len(prices)
"""
        with pytest.raises(ValueError, match="not allowed"):
            run_sandboxed(code, [100.0, 101.0], {})

    def test_sandbox_blocks_file_io(self):
        code = """
def simulate(prices, params):
    assert open is None
    return [1.0] * len(prices)
"""
        result = run_sandboxed(code, [100.0, 101.0], {})
        assert result == [1.0, 1.0]

    def test_sandbox_blocks_network_imports(self):
        code = """
import requests

def simulate(prices, params):
    return [1.0] * len(prices)
"""
        with pytest.raises(ValueError, match="blocked|not allowed"):
            run_sandboxed(code, [100.0, 101.0], {})

    def test_unsafe_runs_directly(self):
        code = """
import numpy as np

def simulate(prices, params):
    return (np.array(prices) / prices[0]).tolist()
"""
        result = run_unsafe(code, [100.0, 101.0, 102.0], {})
        assert result == [1.0, 1.01, 1.02]

    def test_run_strategy_selects_sandbox(self):
        code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    return (p / p[0]).tolist()
"""
        result = run_strategy(code, [100.0, 101.0], {}, trusted=False)
        assert result == [1.0, 1.01]

    def test_run_strategy_trusted_mode(self):
        code = """
def simulate(prices, params):
    return [1.0] * len(prices)
"""
        result = run_strategy(code, [100.0, 101.0], {}, trusted=True)
        assert result == [1.0, 1.0]
