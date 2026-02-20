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

echo "Strategy response (path): $STRATEGY_RESPONSE"

RUN_RESPONSE=$(curl -s -X POST http://127.0.0.1:8001/runs \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_path\":\"$STRATEGY_PATH\"}")

echo "Run response (path): $RUN_RESPONSE"

SUBMIT_PAYLOAD=$("$ROOT_DIR/.venv312/bin/python" - <<'PY'
import json
from pathlib import Path
code = Path("examples/strategies/buy_and_hold.py").read_text(encoding="utf-8")
print(json.dumps({"name": "demo_submitted_strategy", "code": code}))
PY
)

SUBMIT_RESPONSE=$(curl -s -X POST http://127.0.0.1:8001/strategies/submit \
  -H 'Content-Type: application/json' \
  -d "$SUBMIT_PAYLOAD")

echo "Strategy response (submit): $SUBMIT_RESPONSE"

SUBMIT_VERSION_ID=$("$ROOT_DIR/.venv312/bin/python" -c 'import json,sys; print(json.loads(sys.argv[1])["strategy_version_id"])' "$SUBMIT_RESPONSE")

RUN_SUBMIT_RESPONSE=$(curl -s -X POST http://127.0.0.1:8001/runs \
  -H 'Content-Type: application/json' \
  -d "{\"strategy_version_id\":$SUBMIT_VERSION_ID}")

echo "Run response (submitted code): $RUN_SUBMIT_RESPONSE"

LEADERBOARD=$(curl -s "http://127.0.0.1:8001/leaderboard?dataset_version=$DATASET_VERSION")
echo "Leaderboard: $LEADERBOARD"
