#!/usr/bin/env bash
set -euo pipefail
set -x

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON:-python3}

if "$PYTHON_BIN" -c "import networkx" >/dev/null 2>&1; then
  HAS_NETWORKX=1
else
  HAS_NETWORKX=0
  echo "[validate_dsl_examples] networkx missing; flow execution will be skipped" >&2
fi

EXAMPLE_DIR="$ROOT/examples/dsl/opcua"
OUT_DIR="$ROOT/out/dsl_examples"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

"$PYTHON_BIN" -m tm.cli dsl lint "$EXAMPLE_DIR"
"$PYTHON_BIN" -m tm.cli dsl compile "$EXAMPLE_DIR" --out "$OUT_DIR" --force
"$PYTHON_BIN" -m tm.cli dsl plan "$EXAMPLE_DIR" --dot "$OUT_DIR/plan.dot" --json "$OUT_DIR/plan.json"
"$PYTHON_BIN" -m tm.cli dsl testgen "$EXAMPLE_DIR" --out "$OUT_DIR/fixtures" --max-cases 10 --json
"$PYTHON_BIN" -m tm.cli triggers validate "$OUT_DIR/triggers.yaml"

FLOW_FILE=$("$PYTHON_BIN" - <<'PY'
import json
import sys
from pathlib import Path
out = Path(sys.argv[1])
flow_dir = out / "flows"
for path in flow_dir.glob("*.yaml"):
    print(path)
    break
else:
    print("", end="")
PY
"$OUT_DIR")

INPUT_FILE="$EXAMPLE_DIR/input.json"

if [[ -z "$FLOW_FILE" ]]; then
  echo "No flow artifacts generated" >&2
  exit 1
fi

"$PYTHON_BIN" -m tm.cli run "$FLOW_FILE" -i "@${INPUT_FILE}"
