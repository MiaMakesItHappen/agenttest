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

"$ROOT_DIR/.venv312/bin/python" - <<'PY'
from api.db import init_db
init_db()
print("DB initialized")
PY

"$ROOT_DIR/.venv312/bin/uvicorn" api.main:app --port 8001 >/tmp/agenttest_api.log 2>&1 &
API_PID=$!
trap 'kill "$API_PID" >/dev/null 2>&1 || true' EXIT

echo "Waiting for API..."
until curl -s http://127.0.0.1:8001/health >/dev/null; do
  sleep 1
done

STRATEGY_PATH="$ROOT_DIR/examples/strategies/buy_and_hold.py"
STRATEGY_RESPONSE=$(curl -s -X POST http://127.0.0.1:8001/strategies \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_path\":\"$STRATEGY_PATH\"}")

echo "Strategy response: $STRATEGY_RESPONSE"

RUN_RESPONSE=$(curl -s -X POST http://127.0.0.1:8001/runs \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_path\":\"$STRATEGY_PATH\"}")

echo "Run response: $RUN_RESPONSE"

## --- Agent code-submission flow ---
echo ""
echo "=== Agent Code Submission Flow ==="

SUBMIT_CODE='import numpy as np\n\ndef simulate(prices, params):\n    \"\"\"Simple momentum strategy.\"\"\"\n    p = np.asarray(prices, dtype=float)\n    window = params.get(\"window\", 3)\n    equity = [1.0]\n    position = 0.0\n    for i in range(1, len(p)):\n        if i >= window and p[i] > p[i - window]:\n            position = 1.0\n        else:\n            position = 0.0\n        ret = (p[i] / p[i-1] - 1.0) * position\n        equity.append(equity[-1] * (1.0 + ret))\n    return equity\n'

SUBMIT_RESPONSE=$(curl -s -X POST http://127.0.0.1:8001/strategies/submit \
  -H 'Content-Type: application/json' \
  -d "{\"code\":\"$SUBMIT_CODE\",\"name\":\"momentum_agent\",\"params\":{}}")

echo "Submit response: $SUBMIT_RESPONSE"

# Extract strategy_version_id and run it
SVR_ID=$(echo "$SUBMIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['strategy_version_id'])")

SUBMIT_RUN=$(curl -s -X POST http://127.0.0.1:8001/runs \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_version_id\":$SVR_ID,\"params\":{\"window\":2}}")

echo "Submit-run response: $SUBMIT_RUN"

LEADERBOARD=$(curl -s "http://127.0.0.1:8001/leaderboard?dataset_version=$DATASET_VERSION")
echo "Leaderboard: $LEADERBOARD"
