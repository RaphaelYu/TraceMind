# TM Artifact v0 Overview

This module codifies how a TraceMind artifact moves from a **Candidate** draft through verification, acceptance, and storage.

## Lifecycle highlights
1. **Candidate vs. Accepted**: Candidates are mutable drafts that still need verifier checks (status `candidate`). The verifier rehashes the canonical body, applies schema & rule validation, and emits an immutable Accepted artifact (status `accepted`) with `meta.hashes.body_hash`, `meta.determinism`, and a `produced_by` tag.
2. **Normal form & hashing**: Every artifact body is normalized (map keys sorted, whitespace trimmed, canonical JSON). The verifier computes `body_hash = sha256(normalize(body))` and anchors it inside the envelope so any downstream change requires rehashing.
3. **Verifier + registry + consistency**: `tm.artifacts.verify.verify` enforces mandatory envelope metadata, plan step rules, and canonical hashes; `ArtifactsRegistry` records accepted artifacts in `.tracemind/registry.jsonl`; `check_consistency` then ensures intent bodies, derived artifacts, and invariants do not regress (C1/C2/C3).
4. **CLI coverage**: Use `tm artifacts verify <path>` to run the verifier, `tm artifacts accept <path> --out <dir>` to persist accepted YAML and register it, `tm artifacts diff <current> <previous>` to inspect canonical diffs, and `tm plan lint <plan_path>` to validate reads/writes/triggers.
5. **CI gates**: `.github/workflows/artifacts.yml` calls `scripts/ci_check_artifacts.sh`, which runs the golden tests, plan lint, and CLI verification against the example artifacts so missing reads/writes or hash changes fail PRs.
6. **Golden artifacts**: Examples live in `specs/examples/artifacts_v0/` and the golden test `tests/golden/test_artifacts_golden_v0.py` asserts their hash stays steady and the verifier accepts them.

## Command quick cheatsheet
```bash
# lint a plan descriptor
tm plan lint specs/examples/artifacts_v0/plan_TM-INT-0001.yaml

# verify a candidate artifact
tm artifacts verify specs/examples/artifacts_v0/intent_TM-INT-0001.yaml

# accept and emit canonical artifact + register
tm artifacts accept specs/examples/artifacts_v0/intent_TM-INT-0001.yaml --out accepted

# diff two canonical artifacts
tm artifacts diff accepted/tm-intent-0001.yaml specs/examples/artifacts_v0/intent_TM-INT-0001.yaml
```

Each command accepts `--json` when you need structured reports for automation.
