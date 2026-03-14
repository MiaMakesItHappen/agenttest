"""
End-to-end API tests for the agenttest submission flow.

Tests the full path: submit code → run strategy → check results → leaderboard.
Uses FastAPI's TestClient (no real server needed).

Run with:  python -m pytest tests/ -v
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_STRATEGY_CODE = """
import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    if len(p) == 0:
        return [1.0]
    p0 = p[0] if p[0] != 0 else 1.0
    return (p / p0).tolist()
"""


@pytest.fixture(scope="module")
def dataset_dir(tmp_path_factory):
    """Create a minimal prices.csv dataset for testing."""
    d = tmp_path_factory.mktemp("dataset")
    (d / "prices.csv").write_text("ts,price\n1,100\n2,101\n3,102\n4,103\n5,104\n")
    return str(d)


@pytest.fixture(scope="module")
def strategies_dir(tmp_path_factory):
    """Temp directory for submitted strategy files."""
    return str(tmp_path_factory.mktemp("strategies"))


@pytest.fixture(scope="module")
def client(dataset_dir, strategies_dir, tmp_path_factory):
    """Create a TestClient backed by a fresh SQLite test database."""
    import importlib
    from fastapi.testclient import TestClient

    # Use a temp file for the test database (avoid :memory: cross-connection issues)
    db_path = str(tmp_path_factory.mktemp("db") / "test.sqlite")
    db_url = f"sqlite:///{db_path}"

    # Set all env vars before any import/reload
    os.environ["DATASET_DIR"] = dataset_dir
    os.environ["DATASET_VERSION"] = "v1"
    os.environ["DATABASE_URL"] = db_url
    os.environ["STRATEGIES_DIR"] = strategies_dir

    # Reload api.db first so the engine is created with the test DATABASE_URL
    import api.db as db_mod
    importlib.reload(db_mod)

    # Create all tables on the test engine
    db_mod.init_db()

    # Reload api.main so it picks up the reloaded db_mod and fresh STRATEGIES_DIR
    import api.main as main_mod
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestStrategySubmit:
    def test_submit_strategy_returns_ids(self, client):
        resp = client.post(
            "/strategies/submit",
            json={"code": SIMPLE_STRATEGY_CODE, "name": "test_strategy", "params": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "strategy_id" in data
        assert "strategy_version_id" in data
        assert "code_hash" in data
        assert len(data["code_hash"]) == 64  # SHA-256 hex

    def test_submit_same_code_deduplicates(self, client):
        """Submitting identical code should return the same version."""
        resp1 = client.post(
            "/strategies/submit",
            json={"code": SIMPLE_STRATEGY_CODE, "name": "dedup_test", "params": {}},
        )
        resp2 = client.post(
            "/strategies/submit",
            json={"code": SIMPLE_STRATEGY_CODE, "name": "dedup_test_2", "params": {}},
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["code_hash"] == resp2.json()["code_hash"]
        # Should reuse same strategy_version_id
        assert resp1.json()["strategy_version_id"] == resp2.json()["strategy_version_id"]

    def test_submit_missing_simulate_rejected(self, client):
        bad_code = "def not_simulate(x): return x"
        resp = client.post(
            "/strategies/submit",
            json={"code": bad_code, "name": "bad_strategy", "params": {}},
        )
        assert resp.status_code == 400
        assert "simulate" in resp.json()["detail"].lower()

    def test_submit_empty_code_rejected(self, client):
        resp = client.post(
            "/strategies/submit",
            json={"code": "   ", "name": "empty", "params": {}},
        )
        assert resp.status_code == 400


class TestRunFlow:
    @pytest.fixture(autouse=True)
    def submitted_version(self, client):
        resp = client.post(
            "/strategies/submit",
            json={"code": SIMPLE_STRATEGY_CODE, "name": "run_flow_test", "params": {}},
        )
        assert resp.status_code == 200
        self.version_id = resp.json()["strategy_version_id"]

    def test_run_submitted_strategy(self, client):
        resp = client.post(
            "/runs",
            json={"strategy_version_id": self.version_id, "params": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "run_id" in data
        assert "metrics" in data
        m = data["metrics"]
        assert m["total_return"] == pytest.approx(0.04, rel=1e-3)
        assert m["score"] > 0

    def test_run_then_fetch(self, client):
        run_resp = client.post(
            "/runs",
            json={"strategy_version_id": self.version_id},
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run_id"]

        fetch_resp = client.get(f"/runs/{run_id}")
        assert fetch_resp.status_code == 200
        assert fetch_resp.json()["run_id"] == run_id
        assert fetch_resp.json()["status"] == "completed"

    def test_leaderboard_includes_run(self, client):
        client.post(
            "/runs",
            json={"strategy_version_id": self.version_id},
        )
        lb = client.get("/leaderboard?dataset_version=v1")
        assert lb.status_code == 200
        entries = lb.json()
        assert len(entries) > 0
        assert entries[0]["score"] is not None


class TestSandboxIntegration:
    """Verify that submitted strategies actually go through the sandbox wrapper."""

    def test_submitted_strategy_uses_sandbox_via_runner(self, client, monkeypatch):
        """
        Verify that running a submitted strategy passes trusted=False to run_backtest.
        We patch api.main.run_backtest (where the reference lives after 'from ... import').
        """
        import api.main as main_mod
        import worker.runner as runner_mod
        calls = []

        real_run_backtest = runner_mod.run_backtest

        def spy_run_backtest(*args, trusted=True, **kwargs):
            calls.append(trusted)
            return real_run_backtest(*args, trusted=trusted, **kwargs)

        # Patch where api.main holds the reference (direct import binding)
        monkeypatch.setattr(main_mod, "run_backtest", spy_run_backtest)

        # Fresh submission
        unique_code = SIMPLE_STRATEGY_CODE + "\n# unique marker for spy test"
        submit = client.post(
            "/strategies/submit",
            json={"code": unique_code, "name": "spy_test", "params": {}},
        )
        assert submit.status_code == 200
        version_id = submit.json()["strategy_version_id"]

        client.post("/runs", json={"strategy_version_id": version_id})
        # run_backtest should have been called with trusted=False for submitted code
        assert len(calls) > 0
        assert calls[-1] is False, "Submitted strategy should run with trusted=False"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
