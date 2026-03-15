"""
End-to-end API tests for agent strategy submission flow.

Tests the full path:
  POST /strategies/submit → POST /runs → GET /runs/{id} → GET /leaderboard

Run with: python -m pytest tests/ -v
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Minimal strategy code fragments used across tests
# ---------------------------------------------------------------------------
SIMPLE_STRATEGY = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if p[0] != 0 else 1.0
    return (p / p0).tolist()
"""

INVALID_STRATEGY_NO_SIMULATE = """
import numpy as np

def not_simulate(prices, params):
    return [1.0] * len(prices)
"""

EMPTY_CODE = "   "


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Create a test client with an isolated SQLite DB and dataset dir."""
    tmp = tmp_path_factory.mktemp("agenttest")

    db_path = str(tmp / "test.sqlite")
    dataset_dir = str(tmp / "dataset")
    strategies_dir = str(tmp / "strategies")
    os.makedirs(dataset_dir, exist_ok=True)
    os.makedirs(strategies_dir, exist_ok=True)

    # Minimal prices CSV
    prices_csv = os.path.join(dataset_dir, "prices.csv")
    with open(prices_csv, "w") as f:
        f.write("ts,price\n1,100\n2,101\n3,102\n4,103\n5,104\n")

    # Patch env before importing the app
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DATASET_DIR"] = dataset_dir
    os.environ["DATASET_VERSION"] = "v1"
    os.environ["STRATEGIES_DIR"] = strategies_dir

    # Import app AFTER setting env vars so db/config pick them up
    from api.db import engine, init_db
    from api.models import Base

    # Re-init with test DB
    Base.metadata.create_all(bind=engine)

    from api.main import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests: /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Tests: POST /strategies/submit
# ---------------------------------------------------------------------------


class TestSubmitStrategy:
    def test_submit_valid_strategy(self, client):
        resp = client.post(
            "/strategies/submit",
            json={"code": SIMPLE_STRATEGY, "name": "test_simple", "params": {}},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "strategy_id" in data
        assert "strategy_version_id" in data
        assert "code_hash" in data
        assert len(data["code_hash"]) == 64  # SHA-256 hex digest

    def test_submit_idempotent_same_hash(self, client):
        """Submitting identical code twice returns same version."""
        payload = {"code": SIMPLE_STRATEGY, "name": "dedup_test", "params": {}}
        r1 = client.post("/strategies/submit", json=payload)
        r2 = client.post("/strategies/submit", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["code_hash"] == r2.json()["code_hash"]
        assert r1.json()["strategy_version_id"] == r2.json()["strategy_version_id"]

    def test_submit_rejects_missing_simulate(self, client):
        resp = client.post(
            "/strategies/submit",
            json={
                "code": INVALID_STRATEGY_NO_SIMULATE,
                "name": "bad_strategy",
                "params": {},
            },
        )
        assert resp.status_code == 400
        assert "simulate" in resp.json()["detail"].lower()

    def test_submit_rejects_empty_code(self, client):
        resp = client.post(
            "/strategies/submit",
            json={"code": EMPTY_CODE, "name": "empty", "params": {}},
        )
        assert resp.status_code == 400

    def test_submit_different_code_creates_new_version(self, client):
        code_a = SIMPLE_STRATEGY
        code_b = SIMPLE_STRATEGY + "\n# variant\n"
        r_a = client.post("/strategies/submit", json={"code": code_a, "name": "variant_a"})
        r_b = client.post("/strategies/submit", json={"code": code_b, "name": "variant_b"})
        assert r_a.status_code == 200
        assert r_b.status_code == 200
        assert r_a.json()["code_hash"] != r_b.json()["code_hash"]
        assert r_a.json()["strategy_version_id"] != r_b.json()["strategy_version_id"]


# ---------------------------------------------------------------------------
# Tests: POST /strategies/submit → POST /runs (full submission flow)
# ---------------------------------------------------------------------------


class TestSubmissionRunFlow:
    def test_submit_then_run(self, client):
        """Submit code, then run it end-to-end."""
        # 1. Submit
        submit_resp = client.post(
            "/strategies/submit",
            json={
                "code": SIMPLE_STRATEGY,
                "name": "end_to_end_test",
                "params": {},
            },
        )
        assert submit_resp.status_code == 200, submit_resp.text
        version_id = submit_resp.json()["strategy_version_id"]

        # 2. Run
        run_resp = client.post(
            "/runs",
            json={"strategy_version_id": version_id, "params": {}},
        )
        assert run_resp.status_code == 200, run_resp.text
        run_data = run_resp.json()
        assert run_data["status"] == "completed"
        assert "run_id" in run_data
        assert "metrics" in run_data
        assert run_data["metrics"]["score"] > 0

    def test_run_status_retrievable(self, client):
        """GET /runs/{run_id} returns metrics after completion."""
        # Submit + run
        sub = client.post(
            "/strategies/submit",
            json={"code": SIMPLE_STRATEGY, "name": "run_status_test"},
        )
        vid = sub.json()["strategy_version_id"]
        run = client.post("/runs", json={"strategy_version_id": vid})
        run_id = run.json()["run_id"]

        # Fetch run
        get_run = client.get(f"/runs/{run_id}")
        assert get_run.status_code == 200
        data = get_run.json()
        assert data["status"] == "completed"
        assert data["metrics"] is not None
        assert "sharpe" in data["metrics"]

    def test_leaderboard_includes_submitted_run(self, client):
        """Leaderboard should surface the run after submission."""
        sub = client.post(
            "/strategies/submit",
            json={"code": SIMPLE_STRATEGY, "name": "leaderboard_test"},
        )
        vid = sub.json()["strategy_version_id"]
        run = client.post("/runs", json={"strategy_version_id": vid})
        run_id = run.json()["run_id"]

        leaderboard = client.get("/leaderboard?dataset_version=v1")
        assert leaderboard.status_code == 200
        run_ids = [r["run_id"] for r in leaderboard.json()]
        assert run_id in run_ids

    def test_run_with_unknown_version_id_404(self, client):
        resp = client.post("/runs", json={"strategy_version_id": 999999})
        assert resp.status_code == 404

    def test_run_requires_version_or_path(self, client):
        resp = client.post("/runs", json={"params": {}})
        assert resp.status_code == 400
