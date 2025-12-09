#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${VENV_DIR:-venv}"

if [ ! -d "$VENV_DIR" ]; then
  echo "venv not found at '$VENV_DIR'. Set VENV_DIR or create the env first." >&2
  exit 1
fi

source "$VENV_DIR/bin/activate"

if ! command -v pytest >/dev/null 2>&1; then
  echo "pytest is not installed in '$VENV_DIR'. Install dev deps first (e.g. pip install -e .[dev])." >&2
  exit 2
fi

python -m pytest "$@"
