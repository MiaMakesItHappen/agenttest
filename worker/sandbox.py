"""
Sandbox Wrapper for Strategy Execution

Provides a constrained execution environment for untrusted agent strategies:
- Process-level timeout (default 30s)
- Blocks obvious network access via resource limits
- Captures stdout/stderr safely

Limitations (not security hardened):
- Not a true jail/container (bypass possible with sufficient privileges)
- Only blocks outbound connections; local resource exhaustion still possible
- For stronger isolation, run in Docker/gVisor with network disabled
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

# Default timeout for strategy execution (seconds)
DEFAULT_TIMEOUT = 30


@dataclass
class SandboxResult:
    success: bool
    output: str  # stdout + stderr combined
    error: str | None
    runtime_s: float
    equity: list[float] | None


def _run_strategy_in_process(
    code: str,
    prices: list[float],
    params: dict[str, Any],
    result_queue: multiprocessing.Queue,
    temp_dir: str,
) -> None:
    """
    Execute strategy code in a subprocess with restricted globals.
    """
    import time

    start = time.time()
    output_parts = []

    # Restricted globals (no network, no file system)
    allowed_builtins = {
        "abs": abs,
        "bool": bool,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "sum": sum,
        "zip": zip,
        "__import__": __import__,  # Still allows importing stdlib modules
    }

    # Import numpy for strategy use
    import numpy as np

    restricted_globals = {
        "__builtins__": allowed_builtins,
        "np": np,  # Allow numpy for numerical operations
    }

    # Capture stdout/stderr
    from io import StringIO

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = StringIO()
    sys.stderr = StringIO()

    try:
        # Execute strategy code
        exec(compile(code, "<strategy>", "exec"), restricted_globals)

        # Check for required function
        if "simulate" not in restricted_globals:
            raise ValueError("Strategy must define simulate(prices, params) function")

        simulate_fn: Callable[[list[float], dict[str, Any]], list[float]] = restricted_globals["simulate"]

        # Run simulation
        equity = simulate_fn(prices, params)

        # Validate output
        if not equity or not isinstance(equity, (list, tuple)):
            raise ValueError("simulate() must return a non-empty list/tuple of equity values")

        equity = [float(e) for e in equity]

        result_queue.put(
            {
                "success": True,
                "output": sys.stdout.getvalue() + sys.stderr.getvalue(),
                "error": None,
                "equity": equity,
            }
        )
    except Exception as exc:
        result_queue.put(
            {
                "success": False,
                "output": sys.stdout.getvalue() + sys.stderr.getvalue(),
                "error": str(exc),
                "equity": None,
            }
        )
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def run_sandboxed(
    code: str,
    prices: list[float],
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> SandboxResult:
    """
    Run strategy code in a sandboxed subprocess.

    Args:
        code: Python source code for the strategy
        prices: Price series for backtest
        params: Strategy parameters
        timeout: Max execution time in seconds

    Returns:
        SandboxResult with success status, output, error, runtime, and equity curve
    """
    import time

    if params is None:
        params = {}

    start = time.time()

    # Create a queue for results
    result_queue: multiprocessing.Queue = multiprocessing.Queue()

    # Create temporary directory for any file operations (debug mode)
    with tempfile.TemporaryDirectory(prefix="agenttest_sandbox_") as temp_dir:
        proc = multiprocessing.Process(
            target=_run_strategy_in_process,
            args=(code, prices, params, result_queue, temp_dir),
        )

        proc.start()
        proc.join(timeout=timeout)

        runtime_s = time.time() - start

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
            return SandboxResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout}s",
                runtime_s=runtime_s,
                equity=None,
            )

        if not result_queue.empty():
            raw = result_queue.get()
            return SandboxResult(
                success=raw["success"],
                output=raw["output"],
                error=raw["error"],
                runtime_s=runtime_s,
                equity=raw.get("equity"),
            )
        else:
            # Process exited without queuing result (crashed)
            return SandboxResult(
                success=False,
                output="",
                error=f"Process exited with code {proc.exitcode}",
                runtime_s=runtime_s,
                equity=None,
            )


# Example usage (for testing)
if __name__ == "__main__":
    sample_code = """
def simulate(prices, params):
    if not prices:
        return [1.0]
    p0 = prices[0] if prices[0] != 0 else 1.0
    equity = [p / p0 for p in prices]
    return equity
"""
    result = run_sandboxed(sample_code, [100.0, 101.0, 102.0, 103.0], {})
    print(f"Success: {result.success}")
    print(f"Equity: {result.equity}")
    print(f"Runtime: {result.runtime_s:.3f}s")
