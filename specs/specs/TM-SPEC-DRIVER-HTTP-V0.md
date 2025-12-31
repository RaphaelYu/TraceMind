# TraceMind driver HTTP integration spec (v0)

## Purpose

Describe the expectations for external drivers (e.g., Rust) that interact with `tm-server` over `/api/v1` HTTP. This spec exists so non-Python components can reliably mount workspaces, register artifacts, and drive controller cycles without assuming internal storage details.

## Requirements

1. **Workspace mount/select**
   - Consume `POST /api/v1/workspaces/mount` with the path to `tracemind.workspace.yaml`.
   - Persist the returned `workspace_id` and directory mapping.
   - Optionally call `POST /api/v1/workspaces/select` to make the mounted workspace the default.
2. **Artifact envelope lifecycle**
   - Use `/api/v1/artifacts` to create or update intents/bundles. Submit only `{artifact_type, body}`; the server computes the envelope, runs verification, writes the YAML to `<workspace>/specs/{artifact_type}/...`, and returns the accepted entry/document.
   - Expect HTTP 422 with `errors` when verification requires additional fields.
   - Treat `schema_version`, `body_hash`, and `path` from `entry` as truth when referencing persisted artifacts.
3. **Controller cycle execution**
   - Invoke `POST /api/v1/controller/cycle` with `bundle_artifact_id`, `mode` (`live`|`replay`), optional `dry_run`, `approval_token`, `llm_config_id`, and `workspace_id`.
   - Persist the returned `run_id`, `policy_decisions`, `artifact_output_dir`, and `workspace_id`.
   - Query `/api/v1/runs/{run_id}` to fetch the stored `cycle_report.yaml` and verify generated artifacts (`env_snapshot`, `proposed_change_plan`, `execution_report`).

## Driver safeguards

- Always include `workspace_id` (from the mount response) in query parameters so tm-server resolves the correct directories even if another workspace is selected.
- Do not modify `.tracemind/` contents directly; rely on the HTTP contract to create/update artifacts and registry entries.
- Interpret HTTP error semantics per `docs/api_compat_policy.md`. When tm-server returns `404`/`422`, surface the provided `detail`/`errors` to users and avoid retrying silently.
