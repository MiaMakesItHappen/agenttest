from pathlib import Path

from worker.runner import run_backtest


def _write_dataset(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "prices.csv").write_text("ts,price\n1,100\n2,101\n3,102\n", encoding="utf-8")
    return dataset_dir


def test_run_backtest_uses_sandbox_for_untrusted_strategy(tmp_path: Path):
    dataset_dir = _write_dataset(tmp_path)
    strategy_path = tmp_path / "untrusted.py"
    strategy_path.write_text(
        "def simulate(prices, params):\n"
        "    assert open is None\n"
        "    return [1.0 for _ in prices]\n",
        encoding="utf-8",
    )

    result = run_backtest(
        strategy_path=str(strategy_path),
        dataset_dir=str(dataset_dir),
        dataset_version="v1",
        params={},
        trusted_strategy=False,
    )
    assert result.metrics["total_return"] == 0.0


def test_run_backtest_trusted_strategy_skips_sandbox(tmp_path: Path):
    dataset_dir = _write_dataset(tmp_path)
    strategy_path = tmp_path / "trusted.py"
    strategy_path.write_text(
        "def simulate(prices, params):\n"
        "    assert open is not None\n"
        "    return [1.0 for _ in prices]\n",
        encoding="utf-8",
    )

    result = run_backtest(
        strategy_path=str(strategy_path),
        dataset_dir=str(dataset_dir),
        dataset_version="v1",
        params={},
        trusted_strategy=True,
    )
    assert result.metrics["score"] == 0.0
