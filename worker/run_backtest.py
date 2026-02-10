import argparse
from worker.runner import run_backtest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--dataset-version", default="v1")
    args = ap.parse_args()

    res = run_backtest(
        strategy_path=args.strategy,
        dataset_dir=args.dataset,
        dataset_version=args.dataset_version,
        params={},
    )
    print(res.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
