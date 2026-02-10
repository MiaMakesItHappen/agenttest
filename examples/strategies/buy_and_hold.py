import numpy as np

def simulate(prices, params):
    # Equity is just normalized price (buy at start, hold)
    p = np.asarray(prices, dtype=float)
    p0 = p[0] if p[0] != 0 else 1.0
    equity = p / p0
    return equity
