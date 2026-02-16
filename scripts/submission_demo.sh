#!/usr/bin/env bash
set -euo pipefail
#
# agenttest_submission_demo.sh
#
# Demonstrates the agent submission flow:
# 1. Submit strategy code directly
# 2. Run the strategy
# 3. View results on leaderboard
#

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DATASET_DIR="/tmp/agenttest_dataset"
export DATASET_VERSION="v1"
# Use absolute path for SQLite - database must be writable
export DATABASE_URL="sqlite:///${ROOT_DIR}/agenttest.sqlite"
export STRATEGIES_DIR="${ROOT_DIR}/strategies"

mkdir -p "$DATASET_DIR" "$STRATEGIES_DIR"
cat > "$DATASET_DIR/prices.csv" <<'EOF'
ts,price
1,100
2,101
3,102
4,103
5,104
EOF

# Remove old database for clean demo
rm -f "${ROOT_DIR}/agenttest.sqlite"

echo "=== Agenttest Submission Demo ==="

# Start API in background with reload for development
uvicorn api.main:app --reload --port 8000 >/tmp/agenttest_api.log 2>&1 &
API_PID=$!
trap 'kill "$API_PID"' EXIT
echo "Starting API (PID: $API_PID)..."

# Wait for API (reload takes longer)
for i in {1..60}; do
    if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "API ready"
        break
    fi
    sleep 0.5
done

# Test 1: Submit strategy code directly
echo ""
echo "=== Step 1: Submit Strategy Code ==="
SUBMIT_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/strategies/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "code": "import numpy as np\n\ndef simulate(prices, params):\n    p = np.asarray(prices, dtype=float)\n    # Simple moving average crossover\n    window = params.get(\"window\", 5)\n    if len(p) < window:\n        return (p / p[0]).tolist() if p[0] != 0 else [1.0] * len(p)\n    sma_short = np.convolve(p, np.ones(window), \"valid\") / window\n    sma_long = np.convolve(p, np.ones(window * 2), \"valid\") / (window * 2)\n    equity = np.ones(len(p))\n    position = 0\n    for i in range(window * 2 - 1, len(p)):\n        if i >= len(sma_short):\n            continue\n        signal = sma_short[i - window + 1] - sma_long[i - window * 2 + 1]\n        if signal > 0 and position == 0:\n            position = 1\n        elif signal < 0 and position == 1:\n            position = 0\n        equity[i] = 1 + position * (p[i] / p[window * 2 - 1] - 1)\n    return equity.tolist()",
    "name": "sma_crossover_test",
    "params": {"window": 3}
  }')
echo "Submit response: $SUBMIT_RESPONSE"

STRATEGY_VERSION_ID=$(echo "$SUBMIT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['strategy_version_id'])")
echo "Strategy version ID: $STRATEGY_VERSION_ID"

# Test 2: Run the submitted strategy
echo ""
echo "=== Step 2: Run Strategy ==="
RUN_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_version_id\": $STRATEGY_VERSION_ID, \"params\": {\"window\": 3}}")
echo "Run response: $RUN_RESPONSE"

RUN_ID=$(echo "$RUN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['run_id'])")
echo "Run ID: $RUN_ID"

# Test 3: Check run status
echo ""
echo "=== Step 3: Check Run Status ==="
for i in {1..10}; do
    STATUS=$(curl -s "http://127.0.0.1:8000/runs/$RUN_ID" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
    echo "Status: $STATUS"
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
        break
    fi
    sleep 1
done

# Test 4: View metrics
echo ""
echo "=== Step 4: Run Metrics ==="
curl -s "http://127.0.0.1:8000/runs/$RUN_ID" | python3 -c "import sys, json; d = json.load(sys.stdin); print(f\"Score: {d['metrics']['score']:.2f}\"); print(f\"Total Return: {d['metrics']['total_return']*100:.2f}%\"); print(f\"Sharpe: {d['metrics']['sharpe']:.2f}\")"

# Test 5: View leaderboard
echo ""
echo "=== Step 5: Leaderboard ==="
curl -s "http://127.0.0.1:8000/leaderboard?dataset_version=$DATASET_VERSION" | python3 -c "import sys, json; rows = json.load(sys.stdin); [print(f\"{i+1}. score={r['score']:.2f}, strategy={r['strategy_version_id']}\") for i, r in enumerate(rows[:5])]"

echo ""
echo "=== Demo Complete ==="
