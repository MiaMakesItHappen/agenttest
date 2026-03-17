from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import SessionLocal, init_db
from api.models import (
    DatasetVersion,
    DefaultStrategyHistory,
    Run,
    RunMetrics,
    Strategy,
    StrategyVersion,
)
from shared.hashing import sha256_bytes
from worker.runner import run_backtest

app = FastAPI(title="agenttest")


class Health(BaseModel):
    ok: bool = True


class StrategyCreate(BaseModel):
    strategy_path: str


class StrategySubmit(BaseModel):
    code: str
    name: str
    params: Dict[str, Any] = Field(default_factory=dict)


class StrategyCreateResponse(BaseModel):
    strategy_id: int
    strategy_version_id: int
    code_hash: str


class RunCreate(BaseModel):
    strategy_version_id: Optional[int] = None
    strategy_path: Optional[str] = None
    dataset_version: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class PromoteDefault(BaseModel):
    strategy_version_id: int


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_file(path: str) -> str:
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def get_strategy_name(strategy_path: str) -> str:
    return os.path.splitext(os.path.basename(strategy_path))[0]


STRATEGIES_DIR = os.getenv("STRATEGIES_DIR", "strategies")


def ensure_strategies_dir():
    """Ensure the strategies directory exists."""
    os.makedirs(STRATEGIES_DIR, exist_ok=True)


def save_strategy_code(code: str, name: str) -> str:
    """
    Save strategy code to the strategies directory.

    Args:
        code: Python source code for the strategy
        name: Strategy name (used for filename)

    Returns:
        Absolute path to the saved strategy file
    """
    ensure_strategies_dir()
    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    filename = f"{safe_name}.py"
    path = os.path.abspath(os.path.join(STRATEGIES_DIR, filename))
    with open(path, "w") as f:
        f.write(code)
    return path


def get_or_create_strategy_version(db: Session, strategy_path: str) -> StrategyVersion:
    if not os.path.exists(strategy_path):
        raise HTTPException(status_code=400, detail="strategy_path not found")
    code_hash = hash_file(strategy_path)
    existing = db.execute(
        select(StrategyVersion).where(
            StrategyVersion.strategy_path == strategy_path, StrategyVersion.code_hash == code_hash
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    strategy = Strategy(name=get_strategy_name(strategy_path))
    db.add(strategy)
    db.flush()
    version = StrategyVersion(strategy_id=strategy.id, code_hash=code_hash, strategy_path=strategy_path)
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health", response_model=Health)
def health():
    return Health()


@app.post("/strategies", response_model=StrategyCreateResponse)
def create_strategy(req: StrategyCreate, db: Session = Depends(get_db)):
    version = get_or_create_strategy_version(db, req.strategy_path)
    return StrategyCreateResponse(
        strategy_id=version.strategy_id, strategy_version_id=version.id, code_hash=version.code_hash
    )


@app.post("/strategies/submit", response_model=StrategyCreateResponse)
def submit_strategy(req: StrategySubmit, db: Session = Depends(get_db)):
    """
    Submit strategy code directly.

    Saves the code to the strategies/ directory and creates a
    StrategyVersion record with the computed code_hash.

    Request body:
    - code: Python source code with simulate(prices, params) function
    - name: Strategy name (used for filename)
    - params: Optional default parameters

    Returns:
    - strategy_id: Database ID of the strategy
    - strategy_version_id: ID of this specific version
    - code_hash: SHA-256 hash of the submitted code
    """
    if not req.code or not req.code.strip():
        raise HTTPException(status_code=400, detail="code is required")

    # Validate code has required function
    if "def simulate(" not in req.code:
        raise HTTPException(status_code=400, detail="code must contain simulate(prices, params) function")

    # Save code to disk
    strategy_path = save_strategy_code(req.code, req.name)

    # Compute hash and create version
    code_hash = sha256_bytes(req.code.encode("utf-8"))

    # Check for existing version with same hash
    existing = db.execute(
        select(StrategyVersion).where(StrategyVersion.code_hash == code_hash)
    ).scalar_one_or_none()

    if existing:
        # Remove the duplicate file we just wrote
        os.remove(strategy_path)
        return StrategyCreateResponse(
            strategy_id=existing.strategy_id,
            strategy_version_id=existing.id,
            code_hash=existing.code_hash,
        )

    # Create new strategy and version
    strategy = Strategy(name=req.name)
    db.add(strategy)
    db.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        code_hash=code_hash,
        strategy_path=strategy_path,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return StrategyCreateResponse(
        strategy_id=version.strategy_id,
        strategy_version_id=version.id,
        code_hash=version.code_hash,
    )


@app.post("/runs")
def create_run(req: RunCreate, db: Session = Depends(get_db)):
    dataset_dir = os.getenv("DATASET_DIR")
    if not dataset_dir:
        raise HTTPException(status_code=500, detail="DATASET_DIR is not configured")

    dataset_version = req.dataset_version or os.getenv("DATASET_VERSION", "v1")

    if req.strategy_version_id is None and req.strategy_path is None:
        raise HTTPException(status_code=400, detail="Provide strategy_version_id or strategy_path")

    if req.strategy_version_id is not None:
        version = db.get(StrategyVersion, req.strategy_version_id)
        if not version:
            raise HTTPException(status_code=404, detail="strategy_version_id not found")
        # Strategies submitted via /strategies/submit are agent code — run sandboxed
        trusted = False
    else:
        version = get_or_create_strategy_version(db, req.strategy_path)
        # Strategies registered by local file path are assumed trusted (local dev)
        trusted = True

    run_id = str(uuid.uuid4())
    run = Run(
        id=run_id,
        strategy_version_id=version.id,
        dataset_version=dataset_version,
        status="running",
    )
    db.add(run)
    db.commit()

    try:
        result = run_backtest(
            strategy_path=version.strategy_path,
            dataset_dir=dataset_dir,
            dataset_version=dataset_version,
            params=req.params,
            run_id=run_id,
            trusted=trusted,
        )
    except Exception as exc:
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        db.add(run)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    run.dataset_hash = result.dataset_hash
    run.config_hash = result.config_hash
    run.artifacts_dir = result.artifacts_dir
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    db.add(run)

    ds = db.execute(select(DatasetVersion).where(DatasetVersion.version == dataset_version)).scalar_one_or_none()
    if ds is None:
        ds = DatasetVersion(version=dataset_version, dataset_hash=result.dataset_hash)
        db.add(ds)
    elif ds.dataset_hash != result.dataset_hash:
        ds.dataset_hash = result.dataset_hash

    metrics = result.metrics
    run_metrics = RunMetrics(
        run_id=run.id,
        total_return=float(metrics.get("total_return", 0.0)),
        cagr=float(metrics.get("cagr", 0.0)),
        max_drawdown=float(metrics.get("max_drawdown", 0.0)),
        volatility=float(metrics.get("volatility", 0.0)),
        sharpe=float(metrics.get("sharpe", 0.0)),
        liquidation_events=int(metrics.get("liquidation_events", 0)),
        capital_efficiency=float(metrics.get("capital_efficiency", 0.0)),
        score=float(metrics.get("score", 0.0)),
        runtime_s=float(metrics.get("runtime_s", 0.0)),
    )
    db.add(run_metrics)
    db.commit()

    return {
        "run_id": run.id,
        "strategy_version_id": run.strategy_version_id,
        "dataset_version": run.dataset_version,
        "dataset_hash": run.dataset_hash,
        "config_hash": run.config_hash,
        "status": run.status,
        "artifacts_dir": run.artifacts_dir,
        "metrics": {
            "total_return": run_metrics.total_return,
            "cagr": run_metrics.cagr,
            "max_drawdown": run_metrics.max_drawdown,
            "volatility": run_metrics.volatility,
            "sharpe": run_metrics.sharpe,
            "liquidation_events": run_metrics.liquidation_events,
            "capital_efficiency": run_metrics.capital_efficiency,
            "score": run_metrics.score,
            "runtime_s": run_metrics.runtime_s,
        },
    }


@app.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    metrics = run.metrics
    metrics_payload = None
    if metrics:
        metrics_payload = {
            "total_return": metrics.total_return,
            "cagr": metrics.cagr,
            "max_drawdown": metrics.max_drawdown,
            "volatility": metrics.volatility,
            "sharpe": metrics.sharpe,
            "liquidation_events": metrics.liquidation_events,
            "capital_efficiency": metrics.capital_efficiency,
            "score": metrics.score,
            "runtime_s": metrics.runtime_s,
        }
    return {
        "run_id": run.id,
        "strategy_version_id": run.strategy_version_id,
        "dataset_version": run.dataset_version,
        "dataset_hash": run.dataset_hash,
        "config_hash": run.config_hash,
        "status": run.status,
        "artifacts_dir": run.artifacts_dir,
        "metrics": metrics_payload,
    }


@app.get("/leaderboard")
def leaderboard(dataset_version: str = "v1", db: Session = Depends(get_db)):
    rows = (
        db.execute(
            select(Run, RunMetrics)
            .join(RunMetrics, RunMetrics.run_id == Run.id)
            .where(Run.dataset_version == dataset_version, Run.status == "completed")
            .order_by(RunMetrics.score.desc())
        )
        .all()
    )
    return [
        {
            "run_id": run.id,
            "strategy_version_id": run.strategy_version_id,
            "dataset_version": run.dataset_version,
            "score": metrics.score,
            "total_return": metrics.total_return,
            "cagr": metrics.cagr,
            "max_drawdown": metrics.max_drawdown,
            "volatility": metrics.volatility,
            "sharpe": metrics.sharpe,
        }
        for run, metrics in rows
    ]


@app.post("/defaults/promote")
def promote_default(req: PromoteDefault, db: Session = Depends(get_db)):
    version = db.get(StrategyVersion, req.strategy_version_id)
    if not version:
        raise HTTPException(status_code=404, detail="strategy_version_id not found")
    history = DefaultStrategyHistory(strategy_version_id=version.id)
    db.add(history)
    db.commit()
    return {"ok": True, "strategy_version_id": version.id}


@app.get("/rates/aave")
def get_aave_rates(symbol: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    """Get latest Aave v3 Arbitrum rates. Optionally filter by symbol (WBTC, WETH, USDC)."""
    from api.models import AaveRate
    from sqlalchemy import desc
    q = db.query(AaveRate)
    if symbol:
        q = q.filter(AaveRate.symbol == symbol.upper())
    rates = q.order_by(desc(AaveRate.collected_at)).limit(limit).all()
    return [
        {
            "collected_at": r.collected_at.isoformat(),
            "symbol": r.symbol,
            "supply_apy": r.supply_apy,
            "borrow_apy": r.borrow_apy,
            "tvl_usd": r.tvl_usd,
        }
        for r in rates
    ]

