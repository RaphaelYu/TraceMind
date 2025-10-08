#!/usr/bin/env bash
set -euo pipefail
TM_CFG="examples/validation.toml"
FLOW="examples/agents/data_cleanup/flows/data_cleanup.yaml"
INPUT='{"input_file":"examples/agents/data_cleanup/data/sample-small.csv"}'

# shellcheck disable=SC2086 # we intentionally want word splitting for INPUT JSON
timeout 120s tm --config "${TM_CFG}" run "${FLOW}" -i "${INPUT}" --direct
echo "OK: data_cleanup example finished"
