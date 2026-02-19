import numpy as np

def simulate(prices, params):
    """Simple momentum strategy."""
    p = np.asarray(prices, dtype=float)
    window = params.get("window", 3)
    equity = [1.0]
    position = 0.0
    for i in range(1, len(p)):
        if i >= window and p[i] > p[i - window]:
            position = 1.0
        else:
            position = 0.0
        ret = (p[i] / p[i-1] - 1.0) * position
        equity.append(equity[-1] * (1.0 + ret))
    return equity
