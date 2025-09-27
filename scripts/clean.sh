#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/clean.sh [--dry-run]

Safely remove ignored build/cache artifacts. Run with --dry-run to preview the
files that would be deleted (uses `git clean -fdX -n`). Without --dry-run the
script asks for confirmation before running `git clean -fdX`.
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

if [[ ${1:-} == "--dry-run" ]]; then
  git clean -fdX -n
  exit 0
fi

echo "This will run 'git clean -fdX' and remove all ignored files (build/cache/data)."
read -r -p "Continue? [y/N] " reply
if [[ ! $reply =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 1
fi

git clean -fdX
