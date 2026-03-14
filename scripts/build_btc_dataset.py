#!/usr/bin/env python3
"""
Build a BTC price dataset for backtesting using Kraken public API.
Saves daily OHLCV closes to examples/datasets/btc_daily/prices.csv
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "examples" / "datasets" / "btc_daily"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "prices.csv"

# Kraken free public API — daily (1440 min) OHLCV, ~720 candles max
# since=0 gets oldest available
KRAKEN_URL = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440"

def fetch():
    req = urllib.request.Request(KRAKEN_URL, headers={"User-Agent": "agenttest-dataset/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def main():
    print("Fetching BTC daily prices from Kraken (~720 days)...")
    data = fetch()
    if data.get("error"):
        raise RuntimeError(f"Kraken error: {data['error']}")

    result = data.get("result", {})
    # Key is the pair name — grab the first non-'last' key
    pair_key = next(k for k in result if k != "last")
    candles = result[pair_key]
    print(f"Got {len(candles)} candles")

    rows = []
    for c in candles:
        ts = int(c[0])
        close = float(c[4])
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append((dt.strftime("%Y-%m-%dT%H:%M:%SZ"), round(close, 2)))

    with open(OUT_FILE, "w") as f:
        f.write("ts,price\n")
        for ts, p in rows:
            f.write(f"{ts},{p}\n")

    print(f"Saved {len(rows)} rows to {OUT_FILE}")
    print(f"Date range: {rows[0][0]} → {rows[-1][0]}")
    print(f"Price range: ${min(r[1] for r in rows):,.0f} → ${max(r[1] for r in rows):,.0f}")

if __name__ == "__main__":
    main()
