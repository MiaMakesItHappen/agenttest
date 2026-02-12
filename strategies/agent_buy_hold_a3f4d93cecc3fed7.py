
def simulate(prices, params):
    # Convert to list if it's a pandas Series or numpy array
    if hasattr(prices, "tolist"):
        prices_list = prices.tolist()
    else:
        prices_list = list(prices)
    
    if not prices_list:
        return [1.0]
    
    p0 = float(prices_list[0])
    if p0 == 0:
        p0 = 1.0
    
    equity = [float(p) / p0 for p in prices_list]
    return equity
