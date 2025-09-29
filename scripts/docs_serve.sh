#!/usr/bin/env bash
set -euo pipefail
if ! command -v mkdocs >/dev/null 2>&1; then
  echo "mkdocs not found. Install with: pip install mkdocs"
  exit 1
fi
mkdocs serve -a 0.0.0.0:8000
