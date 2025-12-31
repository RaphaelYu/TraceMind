# Polyglot integration guide: Rust driver ↔ TraceMind via HTTP

This guide explains how a Rust-based controller driver can interact with `tm-server` without deep knowledge of TraceMind internals. Treat the HTTP surface described by `docs/tm_server_api_v1.md` and `docs/api_compat_policy.md` as the contract.

## Driver responsibility overview

1. **Workspace selection** – mount or switch to an existing workspace via `/api/v1/workspaces/mount` and `/api/v1/workspaces/select`. The driver should reuse the returned `workspace_id` for every subsequent request so tm-server knows where to persist artifacts, reports, and registry state.
2. **Artifact registration** – before executing a cycle, register or update the intent/bundle artifacts with `/api/v1/artifacts` so tm-server can source the accepted YAML from `<workspace>/specs/...`. The driver only sends `{artifact_type, body}`; tm-server builds the envelope, runs `verify()`, and stores the canonical document plus `body_hash`.
3. **Cycle execution** – call `/api/v1/controller/cycle` (or `/api/controller/cycle` as a legacy alias) when you have an accepted bundle. Provide `bundle_artifact_id`, choose `mode` (`live`/`replay`), optionally include `dry_run`, `workspace_id`, `approval_token`, and `llm_config_id`, and trust tm-server to persist the report + controller artifacts.
4. **Post-run observation** – fetch `/api/v1/runs/{run_id}` and `/api/v1/controller/cycle` responses to understand the generated plan, gap/backlog documents, and policy decisions. Use `/api/v1/artifacts/{artifact_id:path}` if you need any artifact payload stored under `<workspace>/specs`.

## Endpoints the Rust driver calls

| Purpose | Endpoint | Key inputs | Notable outputs |
|---|---|---|---|
| Mount/select workspace | `POST /api/v1/workspaces/mount` + `POST /api/v1/workspaces/select` | workspace manifest path or ID | `workspace_id`, `directories`, `commit_policy` |
| List existing artifacts | `GET /api/v1/artifacts` | `workspace_id`, optional `artifact_type` | registry entries (artifact ID/type/hash/path) |
| Fetch single artifact | `GET /api/v1/artifacts/{artifact_id:path}` | `artifact_id`, `workspace_id` | `entry` + stored `document` (envelope+body) |
| Create/update artifact | `POST/PUT /api/v1/artifacts` | `{artifact_type, body}`, `workspace_id` query | accepted `entry` + persisted `document`, `body_hash` |
| Run controller cycle | `POST /api/v1/controller/cycle` | `bundle_artifact_id`, `mode`, `workspace_id`, optional tokens/configs | cycle result + report metadata |
| Retrieve run report | `GET /api/v1/runs/{run_id}` | `run_id`, `workspace_id` | stored `cycle_report.yaml` contents |

Ensure the driver gracefully surfaces HTTP 4xx/5xx errors and interprets `detail` or `errors` payloads. For artifact validation failures, tm-server returns HTTP 422 with `errors` describing schema/location.

## Artifact expectations

- The driver only crafts the `body` for the desired artifact (typically `intent` or `agent_bundle`). `intent_id` or `bundle_id` is required and drives the final artifact ID.
- Every artifact entry returned by `/api/v1/artifacts` includes `body_hash`, `schema_version`, and `path`. `path` points to the YAML file under `<workspace>/specs/...`.
- Store the driver-generated intent/bundle under `<workspace>/specs` so `tm-server` can verify and reference it later. Accept/verify happens server-side; the driver does not touch `.tracemind/registry.jsonl` directly.

## Selecting the workspace directory

1. Keep a trusted copy of the workspace manifest path and mount it via `/api/v1/workspaces/mount`.
2. Persist the returned descriptor (workspace ID + directory map). Use `directories.specs` and `directories.artifacts` if the driver needs local file snapshots.
3. When running multiple drivers or contexts, call `/api/v1/workspaces/select` to mark which workspace tm-server should treat as “current.” All other endpoints accept `workspace_id` as a query parameter, but selection gives a sensible default.

## Run report format

`/api/v1/controller/cycle` returns a JSON payload containing:

```json
{
  "run_id": "...",
  "mode": "live",
  "dry_run": false,
  "success": true,
  "generated_at": "...",
  "bundle_artifact_id": "...",
  "env_snapshot": "...",
  "proposed_change_plan": "...",
  "execution_report": "...",
  "start_time": "...",
  "end_time": "...",
  "duration_seconds": 0,
  "policy_decisions": [ { "effect": "...", "target": "...", "allowed": true, "reason": "..." } ],
  "errors": [],
  "artifact_output_dir": "...",
  "workspace_id": "...",
  "llm_config_id": "...",
  "llm_config": { ... }
}
```

`GET /api/v1/runs/{run_id}` returns the YAML persisted under `<workspace>/reports/runs/{run_id}/cycle_report.yaml` with matching keys. Use these results to confirm policy decisions, plan identifiers, and artifact hashes without reading internal state.
