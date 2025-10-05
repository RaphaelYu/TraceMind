#!/usr/bin/env bash
set -euo pipefail
python -m pip install -U pip build twine
python -m build && twine check dist/*
python - <<'PY'
from tm.plugins.loader import load
print("Loader OK")
print("OK: release smoke")
PY
