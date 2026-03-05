"""Tests for strategy code submission API flow."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import db
import api.main as main_api
from api.main import app
from api.models import Base


def _setup_test_db(tmp_path: Path) -> None:
    """Point app DB globals at a fresh sqlite database for this test."""
    db_path = tmp_path / "test_agenttest.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    db.engine = engine
    db.SessionLocal = TestingSessionLocal
    main_api.SessionLocal = TestingSessionLocal

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_submit_and_run_strategy(tmp_path: Path, monkeypatch):
    """End-to-end: submit strategy code, then run by strategy_version_id."""
    _setup_test_db(tmp_path)

    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "prices.csv").write_text("ts,price\n1,100\n2,101\n3,102\n4,103\n")

    strategies_dir = tmp_path / "strategies"

    monkeypatch.setenv("DATASET_DIR", str(dataset_dir))
    monkeypatch.setenv("DATASET_VERSION", "v1")
    monkeypatch.setenv("STRATEGIES_DIR", str(strategies_dir))

    client = TestClient(app)

    submit = client.post(
        "/strategies/submit",
        json={
            "name": "simple_submit",
            "code": "import numpy as np\n\ndef simulate(prices, params):\n    p=np.asarray(prices,dtype=float)\n    p0=p[0] if p[0] != 0 else 1.0\n    return (p/p0).tolist()\n",
            "params": {},
        },
    )
    assert submit.status_code == 200
    payload = submit.json()
    assert payload["strategy_id"] > 0
    assert payload["strategy_version_id"] > 0
    assert len(payload["code_hash"]) == 64

    strategy_file = strategies_dir / "simple_submit.py"
    assert strategy_file.exists()

    run = client.post(
        "/runs",
        json={"strategy_version_id": payload["strategy_version_id"], "params": {}},
    )
    assert run.status_code == 200
    run_payload = run.json()
    assert run_payload["status"] == "completed"
    assert run_payload["metrics"]["runtime_s"] >= 0


def test_submit_deduplicates_by_code_hash(tmp_path: Path, monkeypatch):
    """Submitting identical code twice should return the first StrategyVersion."""
    _setup_test_db(tmp_path)

    monkeypatch.setenv("STRATEGIES_DIR", str(tmp_path / "strategies"))

    client = TestClient(app)

    body = {
        "name": "dedupe_test",
        "code": "def simulate(prices, params):\n    return [1.0] * len(prices)\n",
        "params": {},
    }

    first = client.post("/strategies/submit", json=body)
    second = client.post("/strategies/submit", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["strategy_version_id"] == second.json()["strategy_version_id"]
    assert first.json()["code_hash"] == second.json()["code_hash"]
