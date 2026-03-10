import os
import tempfile
import unittest
import uuid
from pathlib import Path

from worker.runner import run_backtest


class RunBacktestSandboxIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dataset_dir = Path(self.temp_dir.name) / "dataset"
        self.dataset_dir.mkdir()
        (self.dataset_dir / "prices.csv").write_text("ts,price\n1,100\n2,101\n3,102\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_untrusted_strategy_uses_sandbox(self):
        strategy_path = Path(self.temp_dir.name) / "submitted_strategy.py"
        strategy_path.write_text(
            "def simulate(prices, params):\n"
            "    with open('/tmp/should_not_exist.txt', 'w') as f:\n"
            "        f.write('nope')\n"
            "    return [1.0] * len(prices)\n",
            encoding="utf-8",
        )

        with self.assertRaises(ValueError):
            run_backtest(
                strategy_path=str(strategy_path),
                dataset_dir=str(self.dataset_dir),
                dataset_version="v1",
                params={},
                run_id=str(uuid.uuid4()),
                trusted=False,
            )

    def test_trusted_strategy_path_still_runs(self):
        strategy_path = Path(self.temp_dir.name) / "trusted_strategy.py"
        marker_path = Path(self.temp_dir.name) / "trusted_marker.txt"
        strategy_path.write_text(
            "def simulate(prices, params):\n"
            f"    with open({str(marker_path)!r}, 'w') as f:\n"
            "        f.write('ok')\n"
            "    return [1.0] * len(prices)\n",
            encoding="utf-8",
        )

        result = run_backtest(
            strategy_path=str(strategy_path),
            dataset_dir=str(self.dataset_dir),
            dataset_version="v1",
            params={},
            run_id=str(uuid.uuid4()),
            trusted=True,
        )

        self.assertEqual(result.metrics["total_return"], 0.0)
        self.assertTrue(marker_path.exists())


if __name__ == "__main__":
    unittest.main()
