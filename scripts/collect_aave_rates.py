#!/usr/bin/env python3
"""
Hourly Aave v3 rate collector.
Fetches supply + borrow APY for WBTC, WETH, USDC on Arbitrum via DefiLlama.
Saves to agenttest aave_rates table.

Usage:
  python3 scripts/collect_aave_rates.py
  # Or via cron: 0 * * * * python3 /path/to/scripts/collect_aave_rates.py
"""
import os, sys, json, urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.db import get_engine, SessionLocal, init_db
from api.models import AaveRate
from sqlalchemy import text

LLAMA_POOLS_URL = "https://yields.llama.fi/pools"
# Aave borrow rates via DefiLlama borrow endpoint
LLAMA_BORROW_URL = "https://yields.llama.fi/lendBorrow"

TARGETS = {"WBTC", "WETH", "USDC", "USDT"}


def fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "agenttest-rate-collector/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.load(r)
        return result if isinstance(result, list) else result.get("data", [])


def collect():
    init_db()
    session = SessionLocal()
    now = datetime.now(timezone.utc)

    try:
        # Supply rates
        supply_pools = fetch(LLAMA_POOLS_URL)
        supply_map = {}
        for p in supply_pools:
            if ("aave-v3" in p.get("project", "").lower()
                    and "arbitrum" in p.get("chain", "").lower()
                    and p.get("symbol", "") in TARGETS):
                sym = p["symbol"]
                if sym not in supply_map:
                    supply_map[sym] = {
                        "supply_apy": round(p.get("apy", 0), 6),
                        "tvl_usd": int(p.get("tvlUsd", 0)),
                        "pool_id": p.get("pool", ""),
                        "project": p.get("project", "aave-v3"),
                        "chain": p.get("chain", "Arbitrum"),
                    }

        # Borrow rates
        borrow_pools = fetch(LLAMA_BORROW_URL)
        borrow_map = {}
        for p in borrow_pools:
            if ("aave-v3" in p.get("project", "").lower()
                    and "arbitrum" in p.get("chain", "").lower()
                    and p.get("symbol", "") in TARGETS):
                sym = p["symbol"]
                if sym not in borrow_map:
                    borrow_map[sym] = round(p.get("apyBorrow", 0) or 0, 6)

        saved = 0
        for sym, info in supply_map.items():
            rate = AaveRate(
                collected_at=now,
                symbol=sym,
                project=info["project"],
                chain=info["chain"],
                supply_apy=info["supply_apy"],
                borrow_apy=borrow_map.get(sym),
                tvl_usd=info["tvl_usd"],
                pool_id=info["pool_id"],
            )
            session.add(rate)
            borrow_str = f" | borrow={borrow_map[sym]:.4f}%" if sym in borrow_map else ""
            ts = now.isoformat(timespec='seconds'); sym_supply = info['supply_apy']; sym_tvl = info['tvl_usd']; print(f"[{ts}] {sym}: supply={sym_supply:.4f}%{borrow_str} tvl=${sym_tvl:,}")
            saved += 1

        session.commit()
        print(f"Saved {saved} rates.")
        return saved

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    collect()

