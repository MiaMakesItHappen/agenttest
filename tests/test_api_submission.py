from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app


STRATEGY_CODE = """import numpy as np

def simulate(prices, params):
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if p[0] != 0 else 1.0
    return (p / p0).tolist()
"""


def test_submit_then_run_strategy(tmp_path, monkeypatch):
    dataset_dir = tmp_path / "dataset"
    strategies_dir = tmp_path / "strategies"
    dataset_dir.mkdir()
    strategies_dir.mkdir()

    (dataset_dir / "prices.csv").write_text("ts,price\n1,100\n2,101\n3,102\n")

    monkeypatch.setenv("DATASET_DIR", str(dataset_dir))
    monkeypatch.setenv("DATASET_VERSION", "v1")

    # api.main reads this global, so patch module attribute directly.
    import api.main as main_mod

    monkeypatch.setattr(main_mod, "STRATEGIES_DIR", str(strategies_dir))

    with TestClient(app) as client:
        submit = client.post(
            "/strategies/submit",
            json={"code": STRATEGY_CODE, "name": "agent_submit_test", "params": {}},
        )
        assert submit.status_code == 200
        payload = submit.json()
        assert payload["strategy_version_id"] > 0
        assert payload["code_hash"]

        run = client.post(
            "/runs",
            json={"strategy_version_id": payload["strategy_version_id"], "params": {}},
        )
        assert run.status_code == 200
        run_payload = run.json()
        assert run_payload["status"] == "completed"
        assert "metrics" in run_payload

    saved_files = list(Path(strategies_dir).glob("*.py"))
    assert saved_files, "submitted strategy code should be written to disk"
