#!/usr/bin/env python3
"""
Utility: fetch the latest Aave rates from the local DB.
Returns a dict like:
  {
    "WBTC": {"supply_apy": 0.0005, "borrow_apy": 0.01},
    "USDC": {"supply_apy": 0.015,  "borrow_apy": 0.027},
    "WETH": {"supply_apy": 0.017,  "borrow_apy": 0.023},
    "_collected_at": "2026-03-14T12:03:24+00:00"
  }
Falls back to hardcoded March 2026 values if DB is empty.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

FALLBACK = {
    "WBTC": {"supply_apy": 0.0005,  "borrow_apy": 0.0100},
    "USDC": {"supply_apy": 0.0150,  "borrow_apy": 0.0350},
    "WETH": {"supply_apy": 0.0170,  "borrow_apy": 0.0233},
    "_collected_at": "fallback-hardcoded",
    "_source": "fallback",
}


def get_latest_rates() -> dict:
    try:
        from api.db import SessionLocal, init_db
        from api.models import AaveRate
        from sqlalchemy import select

        init_db()
        session = SessionLocal()
        try:
            # Latest collected_at per symbol
            rows = session.execute(
                select(AaveRate).order_by(AaveRate.collected_at.desc()).limit(20)
            ).scalars().all()

            if not rows:
                return FALLBACK

            latest_ts = rows[0].collected_at
            latest_by_sym = {}
            for r in rows:
                if r.symbol not in latest_by_sym:
                    latest_by_sym[r.symbol] = r

            result = {
                sym: {
                    "supply_apy": round((r.supply_apy or 0) / 100, 8),   # pct -> fraction
                    "borrow_apy": round((r.borrow_apy or 0) / 100, 8),
                }
                for sym, r in latest_by_sym.items()
            }
            result["_collected_at"] = latest_ts.isoformat()
            result["_source"] = "db"
            return result
        finally:
            session.close()
    except Exception as e:
        import sys
        print(f"[get_latest_rates] DB error: {e} — using fallback", file=sys.stderr)
        return FALLBACK


if __name__ == "__main__":
    import json
    rates = get_latest_rates()
    print(json.dumps(rates, indent=2, default=str))
