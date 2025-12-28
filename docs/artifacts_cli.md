# Artifacts CLI

TraceMind exposes a lightweight CLI for the artifact life cycle along with a dedicated plan linting helper.

## `tm artifacts` commands

- `tm artifacts verify <path>`: runs `tm.artifacts.verify.verify` against the supplied YAML/JSON artifact and prints either `accepted` or `rejected` plus any verification errors. Use `--json` to emit the full report payload.
- `tm artifacts accept <path> --out <dir>`: verifies the artifact, writes the accepted document (with `meta.hashes.body_hash`, `meta.determinism`, and `_produced_by` filled) to `<dir>/<artifact_id>.yaml`, registers it in `.tracemind/registry.jsonl`, and prints the verification summary. Use `--registry <file>` to override the registry location and `--json` for machine output.
- `tm artifacts diff <current> <previous>`: compares two artifacts via canonical normalization and prints a unified diff; `--json` returns the machine‑readable diff lines plus canonical payloads.

## `tm plan lint` command

- `tm plan lint <plan_path>`: validates the plan structure for unique/defined steps, required `reads/writes`, rule references, and valid triggers. Issues are printed with their severity, and the command exits nonzero when problems are present. Use `--json` to obtain a list of issue dictionaries.

## Registry note

Accepted artifacts are registered in `.tracemind/registry.jsonl` by default so later commands (diffs, consistency checks, etc.) can look up previous versions by intent, type, or body hash.
