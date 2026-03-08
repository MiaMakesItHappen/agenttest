import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATASET_VERSION", "v1")

from api.main import app  # noqa: E402
from api.db import init_db  # noqa: E402


def test_submit_strategy_persists_file_and_reuses_hash(tmp_path, monkeypatch):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "prices.csv").write_text("""ts,price
1,100
2,101
3,102
""", encoding="utf-8")

    db_path = tmp_path / "test.sqlite"
    strategies_dir = tmp_path / "strategies"

    monkeypatch.setenv("DATASET_DIR", str(dataset_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STRATEGIES_DIR", str(strategies_dir))

    init_db()
    client = TestClient(app)

    # avoid accidental dedupe against an existing workspace DB record
    unique_name = f"mean_reversion_{tmp_path.name}"
    payload = {
        "name": unique_name,
        "code": "import numpy as np\n\ndef simulate(prices, params):\n    p = np.asarray(prices, dtype=float)\n    if len(p) == 0: return [1.0]\n    out = p / (p[0] if p[0] != 0 else 1.0)\n    out[0] = 1.0\n    return out.tolist()",
        "params": {},
    }

    first = client.post("/strategies/submit", json=payload)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["strategy_version_id"] > 0

    saved_files = list(strategies_dir.rglob("*.py"))
    assert len(saved_files) == 1
    assert unique_name in saved_files[0].name

    second = client.post("/strategies/submit", json=payload)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["strategy_version_id"] == first_body["strategy_version_id"]
    assert second_body["code_hash"] == first_body["code_hash"]
    assert len(list(strategies_dir.rglob("*.py"))) == 1


def test_submitted_strategy_can_run_via_strategy_version_id(tmp_path, monkeypatch):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "prices.csv").write_text("""ts,price
1,100
2,103
3,106
""", encoding="utf-8")

    db_path = tmp_path / "run.sqlite"
    strategies_dir = tmp_path / "strategies"

    monkeypatch.setenv("DATASET_DIR", str(dataset_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STRATEGIES_DIR", str(strategies_dir))

    init_db()
    client = TestClient(app)

    submit = client.post(
        "/strategies/submit",
        json={
            "name": "trend_agent",
            "code": "import numpy as np\n\ndef simulate(prices, params):\n    p = np.asarray(prices, dtype=float)\n    if len(p) == 0: return [1.0]\n    out = p / (p[0] if p[0] != 0 else 1.0)\n    out[0] = 1.0\n    return out.tolist()",
            "params": {},
        },
    )
    version_id = submit.json()["strategy_version_id"]

    run = client.post("/runs", json={"strategy_version_id": version_id, "params": {}})
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "completed"
    assert body["strategy_version_id"] == version_id
    assert body["metrics"]["total_return"] > 0
    assert Path(body["artifacts_dir"]).exists()
