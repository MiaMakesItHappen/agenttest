#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DATASET_DIR="${DATASET_DIR:-/tmp/agenttest_dataset}"
export DATASET_VERSION="${DATASET_VERSION:-v1}"
# Default no-Docker path: local SQLite file
export DATABASE_URL="${DATABASE_URL:-sqlite:///./agenttest.sqlite}"
USE_DOCKER="${USE_DOCKER:-0}"

mkdir -p "$DATASET_DIR"
cat > "$DATASET_DIR/prices.csv" <<'CSV'
ts,price
1,100
2,101
3,102
4,103
5,104
CSV

if [[ "$USE_DOCKER" == "1" ]]; then
  export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://agenttest:agenttest@localhost:5432/agenttest}"
  if ! command -v docker >/dev/null 2>&1; then
    echo "USE_DOCKER=1 but docker is not installed." >&2
    exit 1
  fi
  docker compose up -d postgres
  echo "Waiting for Postgres..."
  until docker compose exec -T postgres pg_isready -U agenttest >/dev/null 2>&1; do
    sleep 1
  done
fi

python3 - <<'PY'
from api.db import init_db
init_db()
print("DB initialized")
PY

uvicorn api.main:app --port 8000 >/tmp/agenttest_api.log 2>&1 &
API_PID=$!
trap 'kill "$API_PID" >/dev/null 2>&1 || true' EXIT

echo "Waiting for API..."
until curl -s http://127.0.0.1:8000/health >/dev/null; do
  sleep 1
done

STRATEGY_PATH="$ROOT_DIR/examples/strategies/buy_and_hold.py"
STRATEGY_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/strategies \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_path\":\"$STRATEGY_PATH\"}")

echo "Strategy response: $STRATEGY_RESPONSE"

RUN_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_path\":\"$STRATEGY_PATH\"}")

echo "Run response: $RUN_RESPONSE"

LEADERBOARD=$(curl -s "http://127.0.0.1:8000/leaderboard?dataset_version=$DATASET_VERSION")
echo "Leaderboard: $LEADERBOARD"

# Test agent submission (direct code upload)
echo ""
echo "--- Testing agent submission ---"

# Create JSON payload file to avoid newline escaping issues
AGENT_PAYLOAD=$(python3 <<'PYTHON'
import json

code = """
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
"""

payload = {
    "code": code,
    "name": "agent_buy_hold",
    "metadata": {"author": "test_agent"}
}
print(json.dumps(payload))
PYTHON
)

SUBMIT_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/strategies/submit \
  -H "Content-Type: application/json" \
  -d "$AGENT_PAYLOAD")

echo "Submit response: $SUBMIT_RESPONSE"
SUBMIT_VERSION_ID=$(echo "$SUBMIT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('strategy_version_id', 0))")

if [ "$SUBMIT_VERSION_ID" -gt 0 ] 2>/dev/null; then
  RUN_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/runs \
    -H "Content-Type: application/json" \
    -d "{\"strategy_version_id\": $SUBMIT_VERSION_ID}")
  echo "Run from agent strategy: $RUN_RESPONSE"
else
  echo "Skipping agent run test (submit failed)"
fi
