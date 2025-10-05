#!/usr/bin/env bash
set -euo pipefail
CFG="-c examples/validation.toml"
FLOW="examples/agents/data_cleanup/flows/data_cleanup.yaml"
INPUT='{"input_file":"examples/agents/data_cleanup/data/sample-small.csv"}'
timeout 120s tm ${CFG} run "${FLOW}" -i "${INPUT}" --direct
echo "OK: data_cleanup example finished"
