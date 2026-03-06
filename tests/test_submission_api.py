import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("DATASET_DIR", "/tmp/agenttest_dataset_tests")
os.environ.setdefault("DATASET_VERSION", "v1")
os.environ["DATABASE_URL"] = "sqlite:////tmp/agenttest_test.sqlite"
os.environ["STRATEGIES_DIR"] = "/tmp/agenttest_submitted_strategies"

Path(os.environ["DATASET_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["STRATEGIES_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["DATASET_DIR"]).joinpath("prices.csv").write_text("ts,price\n1,100\n2,101\n3,102\n", encoding="utf-8")
Path(os.environ["DATABASE_URL"].replace("sqlite:///", "")).unlink(missing_ok=True)
for existing in Path(os.environ["STRATEGIES_DIR"]).glob("*.py"):
    existing.unlink()

from api.main import app  # noqa: E402


def test_submit_strategy_persists_hashed_filename_and_reuses_duplicate_hash():
    with TestClient(app) as client:
        code = "def simulate(prices, params):\n    return [1.0 for _ in prices] if prices else [1.0]\n"

        response = client.post(
            "/strategies/submit",
            json={"code": code, "name": "mean reversion v1", "params": {}},
        )
        assert response.status_code == 200
        payload = response.json()
        code_hash = payload["code_hash"]

        strategies_dir = Path(os.environ["STRATEGIES_DIR"])
        expected_prefix = f"mean_reversion_v1_{code_hash[:12]}"
        matches = list(strategies_dir.glob(f"{expected_prefix}.py"))
        if not matches:
            matches = list(strategies_dir.glob("*.py"))
        assert len(matches) == 1
        assert matches[0].name.startswith(expected_prefix)
        assert matches[0].read_text(encoding="utf-8") == code

        duplicate = client.post(
            "/strategies/submit",
            json={"code": code, "name": "mean reversion v1", "params": {}},
        )
        assert duplicate.status_code == 200
        duplicate_payload = duplicate.json()
        assert duplicate_payload["strategy_version_id"] == payload["strategy_version_id"]
        assert duplicate_payload["code_hash"] == code_hash
