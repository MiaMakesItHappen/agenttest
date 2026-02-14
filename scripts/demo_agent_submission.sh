#!/bin/bash
set -e

echo "=== Agent Code Submission Demo ==="
echo ""

# Start API in background
echo "Starting API..."
uvicorn api.main:app --port 8000 &
API_PID=$!
sleep 3

# Trap to cleanup
cleanup() {
    echo "Stopping API..."
    kill $API_PID 2>/dev/null || true
    wait $API_PID 2>/dev/null || true
}
trap cleanup EXIT

BASE_URL="http://localhost:8000"

# Test 1: Submit strategy code
echo "Test 1: Submit strategy code via API"
STRATEGY_CODE='import numpy as np

def simulate(prices, params):
    """Agent-submitted momentum strategy"""
    p = np.asarray(prices, dtype=float)
    if len(p) < 2:
        return np.ones_like(p)
    
    # Simple momentum: buy if price increasing, sell if decreasing
    signals = np.diff(p) > 0
    signals = np.concatenate([[True], signals])  # Start with position
    
    equity = np.ones(len(p))
    for i in range(1, len(p)):
        if signals[i]:
            equity[i] = equity[i-1] * (p[i] / p[i-1])
        else:
            equity[i] = equity[i-1]
    
    return equity
'

STRATEGY_RESPONSE=$(curl -s -X POST "$BASE_URL/strategies" \
  -H "Content-Type: application/json" \
  -d "{\"code\": $(echo "$STRATEGY_CODE" | jq -Rs .), \"name\": \"agent_momentum\"}")

echo "Strategy response: $STRATEGY_RESPONSE"
STRATEGY_VERSION_ID=$(echo "$STRATEGY_RESPONSE" | jq -r '.strategy_version_id')
echo ""

# Test 2: Run the submitted strategy
echo "Test 2: Run the agent-submitted strategy"
RUN_RESPONSE=$(curl -s -X POST "$BASE_URL/runs" \
  -H "Content-Type: application/json" \
  -d "{\"strategy_version_id\": $STRATEGY_VERSION_ID}")

echo "Run response: $RUN_RESPONSE"
RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.run_id')
echo ""

# Test 3: Check leaderboard
echo "Test 3: Fetch leaderboard"
LEADERBOARD=$(curl -s "$BASE_URL/leaderboard?dataset_version=v1")
echo "Leaderboard: $LEADERBOARD"
echo ""

echo "=== Demo completed successfully ==="
