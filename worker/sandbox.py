"""
Sandbox wrapper for strategy execution.

Provides process-level isolation with:
- Execution timeout
- Basic network access blocking (via environment hints)

Limitations:
- This is a lightweight sandbox, NOT a security boundary
- Process can still access filesystem with worker's permissions
- Network blocking is advisory (strategy can bypass if malicious)
- For production: use Docker/gVisor/Firecracker or similar

For MVP purposes, this provides:
- Protection against infinite loops (timeout)
- Discouragement of network calls (subprocess environment)
- Clear contract violation detection
"""

import multiprocessing
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class SandboxResult:
    """Result of sandboxed execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    timeout: bool = False
    runtime_s: float = 0.0


def _run_in_subprocess(
    target_fn: Callable,
    args: tuple,
    kwargs: dict,
    timeout_s: float,
    result_queue: multiprocessing.Queue,
) -> None:
    """Worker process that executes the target function."""
    try:
        # Block common network environment variables (advisory only)
        env_blocklist = [
            "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
            "no_proxy", "NO_PROXY", "ALL_PROXY", "all_proxy"
        ]
        for var in env_blocklist:
            os.environ.pop(var, None)
        
        # Hint to strategy: network is restricted
        os.environ["AGENTTEST_SANDBOX"] = "1"
        os.environ["AGENTTEST_NETWORK_BLOCKED"] = "1"
        
        start = time.time()
        result = target_fn(*args, **kwargs)
        runtime = time.time() - start
        
        result_queue.put(SandboxResult(
            success=True,
            result=result,
            runtime_s=runtime
        ))
    except Exception as e:
        result_queue.put(SandboxResult(
            success=False,
            error=str(e),
            runtime_s=time.time() - start
        ))


def run_sandboxed(
    target_fn: Callable,
    args: tuple = (),
    kwargs: Optional[dict] = None,
    timeout_s: float = 60.0,
) -> SandboxResult:
    """
    Execute a function in a sandboxed subprocess with timeout.
    
    Args:
        target_fn: Function to execute
        args: Positional arguments for target_fn
        kwargs: Keyword arguments for target_fn
        timeout_s: Maximum execution time in seconds
    
    Returns:
        SandboxResult with success status, result/error, and runtime
    """
    if kwargs is None:
        kwargs = {}
    
    ctx = multiprocessing.get_context('spawn')
    result_queue = ctx.Queue()
    
    process = ctx.Process(
        target=_run_in_subprocess,
        args=(target_fn, args, kwargs, timeout_s, result_queue)
    )
    
    start = time.time()
    process.start()
    process.join(timeout=timeout_s)
    runtime = time.time() - start
    
    if process.is_alive():
        # Timeout occurred
        process.terminate()
        process.join(timeout=1.0)
        if process.is_alive():
            process.kill()
            process.join()
        
        return SandboxResult(
            success=False,
            error=f"Execution timeout after {timeout_s}s",
            timeout=True,
            runtime_s=runtime
        )
    
    if not result_queue.empty():
        return result_queue.get()
    
    # Process exited without result (crash?)
    return SandboxResult(
        success=False,
        error=f"Process exited with code {process.exitcode}",
        runtime_s=runtime
    )


def validate_strategy_code(code: str) -> tuple[bool, Optional[str]]:
    """
    Basic validation of strategy code.
    
    Returns:
        (is_valid, error_message)
    """
    # Check for required simulate function
    if "def simulate(" not in code:
        return False, "Strategy must define simulate(prices, params) function"
    
    # Warn about network imports (advisory)
    network_imports = [
        "import requests",
        "import urllib",
        "import http",
        "import socket",
        "from requests",
        "from urllib",
        "from http",
        "from socket",
    ]
    
    for pattern in network_imports:
        if pattern in code:
            return False, f"Network imports are not allowed in sandbox: {pattern}"
    
    return True, None
