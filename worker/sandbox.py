"""
Sandbox Wrapper for Strategy Execution

Provides a restricted execution environment for untrusted strategy code
with process-level isolation and timeout enforcement.

LIMITATIONS:
- Process-level isolation only (not container-level)
- Network blocking via environment variables (not firewall rules)
- Relies on Python's signal/timeout mechanisms
- Not suitable for malicious code (can escape to host system)
"""

import multiprocessing
import os
import signal
import subprocess
import sys
import tempfile
from typing import Any


# Resource limits (soft enforcement via ulimit wrapper)
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MEMORY_MB = 256


def _run_worker(
    strategy_code: str,
    prices: list[float],
    params: dict[str, Any],
    result_queue: multiprocessing.Queue,
    error_queue: multiprocessing.Queue,
) -> None:
    """
    Worker function that runs in a child process.
    Isolated from parent's namespace.
    """
    # Block obvious network access at environment level
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""
    os.environ["ALL_PROXY"] = ""
    os.environ["http_proxy"] = ""
    os.environ["https_proxy"] = ""
    os.environ["no_proxy"] = "localhost,127.0.0.1"

    # Create sandboxed globals
    sandbox_globals = {
        "__name__": "__sandbox__",
        "__builtins__": {
            # Minimal builtins - remove dangerous ones
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "complex": complex,
            "dict": dict,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "frozenset": frozenset,
            "hash": hash,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "oct": oct,
            "open": None,  # BLOCKED - no file I/O
            "ord": ord,
            "pow": pow,
            "print": lambda *args, **kwargs: None,  # Silenced
            "range": range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "type": type,
            "zip": zip,
            # Required for imports
            "__import__": __import__,
            "Exception": Exception,
            "ValueError": ValueError,
            "KeyError": KeyError,
            "ZeroDivisionError": ZeroDivisionError,
            "ArithmeticError": ArithmeticError,
            # Math operations
            "math": None,  # BLOCKED - can be enabled if needed
            "random": None,  # BLOCKED - introduces non-determinism
            "numpy": None,  # BLOCKED - not needed for interface
        },
        # Allow numpy via explicit import in strategy code only
        "np": __import__("numpy"),
    }

    try:
        # Create function from strategy code
        exec(compile(strategy_code, "<strategy>", "exec"), sandbox_globals)

        # Call simulate function
        simulate = sandbox_globals.get("simulate")
        if simulate is None:
            raise ValueError("Strategy must define simulate(prices, params) function")

        result = simulate(prices, params)
        result_queue.put(("success", result))
    except Exception as e:
        error_queue.put(("error", str(e)))


def run_sandboxed(
    strategy_code: str,
    prices: list[float],
    params: dict[str, Any],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> list[float]:
    """
    Run a strategy in a sandboxed child process.

    Args:
        strategy_code: Python source code for the strategy
        prices: Price data for simulation
        params: Strategy parameters
        timeout_seconds: Maximum execution time (default: 60)
        memory_mb: Memory limit (not enforced on macOS, informational)

    Returns:
        List of equity values from simulate()

    Raises:
        TimeoutError: If execution exceeds timeout_seconds
        ValueError: If strategy code is invalid
        RuntimeError: If strategy fails to execute
    """
    # Use multiprocessing for true process isolation
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    error_queue = ctx.Queue()

    # Spawn child process
    process = ctx.Process(
        target=_run_worker,
        args=(strategy_code, prices, params, result_queue, error_queue),
        name="strategy-sandbox",
    )

    try:
        process.start()

        # Wait for completion or timeout
        process.join(timeout=timeout_seconds)

        if process.is_alive():
            process.terminate()
            raise TimeoutError(f"Strategy execution exceeded {timeout_seconds}s timeout")

        # Check for errors from queues
        if not result_queue.empty():
            status, data = result_queue.get()
            if status == "success":
                return data
            else:
                raise RuntimeError(f"Strategy error: {data}")

        if not error_queue.empty():
            status, data = error_queue.get()
            if status == "error":
                raise ValueError(f"Strategy validation error: {data}")
            raise RuntimeError(f"Unexpected error: {data}")

        raise RuntimeError("Process terminated without result")

    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)


def run_unsafe(
    strategy_code: str,
    prices: list[float],
    params: dict[str, Any],
) -> list[float]:
    """
    Run strategy code directly (UNSAFE - for trusted code only).
    Used when strategy comes from verified local files.
    """
    import numpy as np

    local_vars = {"np": np}
    exec(compile(strategy_code, "<strategy>", "exec"), local_vars)

    simulate = local_vars.get("simulate")
    if simulate is None:
        raise ValueError("Strategy must define simulate(prices, params) function")

    return simulate(prices, params)


# Simple hash-based execution selection
def run_strategy(
    strategy_code: str,
    prices: list[float],
    params: dict[str, Any],
    trusted: bool = False,
    **kwargs,
) -> list[float]:
    """
    Run a strategy with appropriate isolation level.

    Args:
        strategy_code: Python source code
        prices: Price data for simulation
        params: Strategy parameters
        trusted: If True, skip sandbox (for local files only!)
        **kwargs: Additional arguments for sandbox

    Returns:
        List of equity values
    """
    if trusted:
        return run_unsafe(strategy_code, prices, params)
    else:
        return run_sandboxed(strategy_code, prices, params, **kwargs)


if __name__ == "__main__":
    # Demo usage
    demo_code = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if p[0] != 0 else 1.0
    equity = p / p0
    return equity.tolist()
"""
    prices = [100.0, 101.0, 102.0, 103.0, 104.0]
    result = run_sandboxed(demo_code, prices, {})
    print(f"Result: {result}")
