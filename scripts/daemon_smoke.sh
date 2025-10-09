#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${DEBUG:-}" ]]; then
  set -x
fi

cleanup() {
  local bin="${TM_BIN:-}"
  if [[ -n "${DAEMON_STATE_DIR:-}" && -d "$DAEMON_STATE_DIR" ]]; then
    if [[ -n "$bin" ]]; then
      TM_ENABLE_DAEMON=1 TM_FILE_QUEUE_V2=1 eval "$bin daemon stop --state-dir \"$DAEMON_STATE_DIR\" --timeout 2" >/dev/null 2>&1 || true
    fi
  fi
  if [[ -n "${SMOKE_TMPDIR:-}" && -d "$SMOKE_TMPDIR" ]]; then
    rm -rf "$SMOKE_TMPDIR"
  fi
}
trap cleanup EXIT

SMOKE_TMPDIR=$(mktemp -d -t tm-daemon-smoke-XXXX)
QUEUE_DIR="$SMOKE_TMPDIR/queue"
IDEM_DIR="$SMOKE_TMPDIR/idempotency"
DLQ_DIR="$SMOKE_TMPDIR/dlq"
DAEMON_STATE_DIR="$SMOKE_TMPDIR/daemon"
LOG_FILE="$DAEMON_STATE_DIR/daemon.log"

export TM_ENABLE_DAEMON=1
export TM_FILE_QUEUE_V2=1

if [[ -n "${TM_BIN:-}" ]]; then
  TM_BIN="${TM_BIN}"
else
  if command -v tm >/dev/null 2>&1; then
    TM_BIN="tm"
  else
    if command -v python3 >/dev/null 2>&1; then
      PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
      PYTHON_BIN="python"
    else
      echo "python interpreter not found" >&2
      exit 1
    fi
    TM_BIN="$PYTHON_BIN -m tm"
  fi
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ "$TM_BIN" == *"python"* ]]; then
    PYTHON_BIN="${TM_BIN%% *}"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    PYTHON_BIN="python3"
  fi
fi

mkdir -p "$QUEUE_DIR" "$IDEM_DIR" "$DLQ_DIR"

cat >"$SMOKE_TMPDIR/flow.json" <<'FLOW'
{
  "flow": {"id": "smoke-flow"},
  "steps": [
    {
      "id": "emit",
      "kind": "task",
      "call": {
        "module": "tm.example.sinks",
        "name": "print_step"
      }
    }
  ]
}
FLOW

start_output=$(eval "$TM_BIN daemon start \
  --state-dir \"$DAEMON_STATE_DIR\" \
  --queue-dir \"$QUEUE_DIR\" \
  --idempotency-dir \"$IDEM_DIR\" \
  --dlq-dir \"$DLQ_DIR\" \
  --workers 1 \
  --log-file \"$LOG_FILE\"")

echo "$start_output"

TM_ENABLE_DAEMON=1 eval "$TM_BIN run \"$SMOKE_TMPDIR/flow.json\" --detached -i '{\"message\":\"daemon-smoke\"}'"

sleep 1

status_json=$(eval "$TM_BIN daemon ps --state-dir \"$DAEMON_STATE_DIR\" --queue-dir \"$QUEUE_DIR\" --json")

echo "$status_json"

STATUS_FILE="$SMOKE_TMPDIR/status.json"
printf '%s\n' "$status_json" >"$STATUS_FILE"

queue_pending=$(STATUS_FILE="$STATUS_FILE" $PYTHON_BIN - <<'PY'
import json
import os
from pathlib import Path
payload = json.loads(Path(os.environ["STATUS_FILE"]).read_text())
queue = payload.get("queue") or {}
value = queue.get("pending") or 0
print(int(value))
PY
)

if [[ "$queue_pending" -lt 0 ]]; then
  echo "unexpected pending count: $queue_pending" >&2
  exit 1
fi

eval "$TM_BIN daemon stop --state-dir \"$DAEMON_STATE_DIR\" --timeout 5"

echo "daemon smoke test OK"
