"""
Crypto Yield Arbitrage Strategy
================================
Hold BTC, borrow USDC against it (40% LTV), earn stablecoin yield on borrowed capital.
Earn: BTC appreciation + BTC supply yield + USDC yield on borrowed amount
Pay: USDC borrow cost
Risk mgmt: exit USDC borrow if BTC drops 20%; re-enter on 10% recovery

Real Aave v3 Arbitrum rates (Mar 2026):
  WBTC supply: ~0.05% APY
  USDC supply: ~1.5% APY  
  USDC borrow: ~3.5% APY (variable)

Net spread on borrowed USDC: 1.5% - 3.5% = -2.0% (borrow costs more than you earn)
Strategy alpha comes from: BTC appreciation + 0.05% BTC yield + risk management
"""
from typing import Any

DAYS_PER_YEAR = 365.0


def default_params() -> dict[str, Any]:
    return {
        "max_ltv": 0.40,
        "btc_supply_apy": 0.0005,   # 0.05% real rate
        "borrow_rate_apy": 0.035,   # 3.5% USDC borrow
        "usdc_yield_apy": 0.015,    # 1.5% USDC supply
        "drawdown_exit_pct": 0.20,  # exit borrow at -20% BTC
        "reentry_pct": 0.10,        # re-enter at +10% recovery
    }


def validate_params(params: dict[str, Any]) -> dict[str, Any]:
    defaults = default_params()
    out = defaults.copy()
    for k, v in params.items():
        if k in defaults and isinstance(v, (int, float)):
            out[k] = float(v)
    out["max_ltv"] = max(0.10, min(0.65, out["max_ltv"]))
    return out


def strategy_name() -> str:
    return "Crypto Yield Arbitrage (BTC Collateral + USDC Borrow)"


def simulate(prices: list[float], params: dict[str, Any]) -> list[float]:
    if not prices or len(prices) < 2:
        return [1.0] * max(len(prices), 1)

    p = validate_params(params)
    btc_daily_yield = (1 + p["btc_supply_apy"]) ** (1 / DAYS_PER_YEAR) - 1
    borrow_daily = (1 + p["borrow_rate_apy"]) ** (1 / DAYS_PER_YEAR) - 1
    usdc_daily = (1 + p["usdc_yield_apy"]) ** (1 / DAYS_PER_YEAR) - 1
    net_spread_daily = usdc_daily - borrow_daily  # negative = costs money

    initial_capital = 1.0  # normalized
    btc_units = initial_capital / prices[0]

    equity = initial_capital
    equity_curve = [1.0]

    position_open = True
    entry_price = prices[0]
    exit_low = None

    for i in range(1, len(prices)):
        price = prices[i]
        prev_price = prices[i - 1]
        btc_value = btc_units * price

        # Risk: drawdown exit
        drawdown = (price - entry_price) / entry_price
        if position_open and drawdown <= -p["drawdown_exit_pct"]:
            position_open = False
            exit_low = price

        # Re-entry
        if not position_open and exit_low is not None:
            if (price - exit_low) / exit_low >= p["reentry_pct"]:
                position_open = True
                entry_price = price
                exit_low = None
        elif not position_open and exit_low is not None:
            exit_low = min(exit_low, price)  # track new lows

        # BTC price return (as fraction of initial capital)
        btc_return = (price - prev_price) / prev_price
        equity *= (1 + btc_return)

        # BTC supply yield (always on)
        equity += equity * btc_daily_yield

        # USDC borrow net P&L (when position open)
        if position_open:
            borrow_amount = btc_value * p["max_ltv"]
            net_daily = borrow_amount * net_spread_daily
            # Express as fraction of current equity
            equity += net_daily / (btc_units * prices[0])

        equity_curve.append(max(equity, 0.001))

    return equity_curve
