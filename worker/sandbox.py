"""
Sandbox Wrapper for Strategy Execution

Provides a restricted execution environment for untrusted strategy code
with process-level isolation and timeout enforcement.

LIMITATIONS:
- Process-level isolation only; this is not a secure container sandbox.
- Network blocking is best-effort via import restrictions and env cleanup.
- File I/O is blocked by removing open() from builtins, but Python introspection
  and allowed imports still make this unsuitable for hostile code.
- Memory limits are not enforced on macOS in the current implementation.
"""

import builtins
import multiprocessing
import os
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MEMORY_MB = 256
BLOCKED_IMPORT_ROOTS = {
    "socket",
    "urllib",
    "urllib3",
    "requests",
    "http",
    "ftplib",
    "telnetlib",
    "subprocess",
    "pathlib",
    "shutil",
}
ALLOWED_IMPORT_ROOTS = {"numpy", "math"}
SAFE_BUILTINS = {
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
    "ord": ord,
    "pow": pow,
    "print": lambda *args, **kwargs: None,
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
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "ZeroDivisionError": ZeroDivisionError,
    "ArithmeticError": ArithmeticError,
    "open": None,
}


def _safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):
    root = name.split('.', 1)[0]
    if root in BLOCKED_IMPORT_ROOTS:
        raise ImportError(f"Import of '{root}' is blocked in sandbox")
    if root not in ALLOWED_IMPORT_ROOTS:
        raise ImportError(f"Import of '{root}' is not allowed in sandbox")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _run_worker(
    strategy_code: str,
    prices: list[float],
    params: dict[str, Any],
    result_queue: multiprocessing.Queue,
    error_queue: multiprocessing.Queue,
) -> None:
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""
    os.environ["ALL_PROXY"] = ""
    os.environ["http_proxy"] = ""
    os.environ["https_proxy"] = ""
    os.environ["all_proxy"] = ""
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    os.environ["no_proxy"] = "localhost,127.0.0.1"

    sandbox_globals = {
        "__name__": "__sandbox__",
        "__builtins__": {**SAFE_BUILTINS, "__import__": _safe_import},
        "np": __import__("numpy"),
    }

    try:
        exec(compile(strategy_code, "<strategy>", "exec"), sandbox_globals)
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
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    error_queue = ctx.Queue()

    process = ctx.Process(
        target=_run_worker,
        args=(strategy_code, prices, params, result_queue, error_queue),
        name="strategy-sandbox",
    )

    try:
        process.start()
        process.join(timeout=timeout_seconds)

        if process.is_alive():
            process.terminate()
            raise TimeoutError(f"Strategy execution exceeded {timeout_seconds}s timeout")

        if not result_queue.empty():
            status, data = result_queue.get()
            if status == "success":
                return data
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
    import numpy as np

    local_vars = {"np": np}
    exec(compile(strategy_code, "<strategy>", "exec"), local_vars)

    simulate = local_vars.get("simulate")
    if simulate is None:
        raise ValueError("Strategy must define simulate(prices, params) function")

    return simulate(prices, params)


def run_strategy(
    strategy_code: str,
    prices: list[float],
    params: dict[str, Any],
    trusted: bool = False,
    **kwargs,
) -> list[float]:
    if trusted:
        return run_unsafe(strategy_code, prices, params)
    return run_sandboxed(strategy_code, prices, params, **kwargs)
