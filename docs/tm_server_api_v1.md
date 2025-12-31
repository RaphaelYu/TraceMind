# TraceMind TM Server API v1

This document describes the **stable `/api/v1` surface**. Follow the compatibility policy in [docs/api_compat_policy.md](api_compat_policy.md) before changing any of these endpoints. The OpenAPI snapshot in `docs/openapi_v1.json` reflects the current contract.

## GET /api/v1/meta

Returns metadata about the tm-server release, API version, supported schema set, and build fingerprint. Useful for diag/logging and client compatibility checks.

### Response
```json
{
  "api_version": "v1",
  "tm_core_version": "X.Y.Z",
  "schemas_supported": ["intent@v0", "..."],
  "build": {
    "git_commit": "deadbeef",
    "build_time": "2025-01-01T00:00:00Z"
  }
}
```

## Workspaces (`/api/v1/workspaces`)

These endpoints let you mount workspace manifests, list mounted workspaces, and query the currently selected workspace.

* `POST /api/v1/workspaces/mount` – Provide `{"path": "/path/to/workspace"}` to mount a workspace. The response includes `workspace_id`, resolved `directories`, and `commit_policy`.
* `GET /api/v1/workspaces` – Lists every mounted workspace descriptor.
* `GET /api/v1/workspaces/current` – Returns the currently selected workspace (or `null` if none).
* `POST /api/v1/workspaces/select` – Set the active workspace via `{"workspace_id": "..."}`.

All responses contain the workspace `directories` so clients can highlight where specs, artifacts, and reports live. Provide `workspace_id` query params on other endpoints to scope them; if omitted they fall back to the selected workspace.

## Artifacts (`/api/v1/artifacts`)

The workspace-aware artifact endpoints operate on accepted artifacts stored under `<workspace>/specs` plus the registry.

* `GET /api/v1/artifacts` – Lists matching registry entries. Optional `artifact_type` filters (intent, agent_bundle, etc.) and `workspace_id` query params are supported. Each item contains `artifact_id`, `artifact_type`, `body_hash`, `path`, and `schema_version`.
* `GET /api/v1/artifacts/{artifact_id:path}` – Fetches the registry entry and the persisted document. The `{artifact_id}` segment supports slashes and returns `entry` plus `document`.
* `POST /api/v1/artifacts` – Create a new intent or bundle by submitting `{"artifact_type": "...", "body": {...}}`. tm-server derives the ID, runs `verify()`, writes the accepted document to `specs/`, updates `.tracemind/registry.jsonl`, and returns the stored artifact detail.
* `PUT /api/v1/artifacts/{artifact_id:path}` – Update an existing artifact with the same body payload. The route re-validates, persists, and returns the updated object.

Validation errors are returned as HTTP 422 with `{"errors": [{"code": "...", "message": "...", "location": "..."}]}` so clients can surface the field-level hints.

## LLM configs (`/api/v1/llm`)

* `GET /api/v1/llm/prompt-templates` – Lists the built-in decision templates that ship with the controller. Use the `version` values when creating configs.
* `GET /api/v1/llm/configs` – Lists saved configs for the workspace. Supply `workspace_id` to scope the lookup.
* `POST /api/v1/llm/configs` – Create a config with `{"model": "...", "prompt_template_version": "...", "prompt_version": "...", "model_id": "...", "model_version": "..."}`. Only `model` and `prompt_template_version` are required.

::
  The response contains `config_id`, `created_at`, and the stored metadata so controller runs can reference the recorded prompt/model fingerprint.

## Controller cycle + run reports

The legacy `/api/controller/*` endpoints remain available as part of the controller workflow, but `/api/v1` now exposes aliased safety wrappers for the stable contract:

* `POST /api/v1/controller/cycle` – Same behavior as `/api/controller/cycle` (preview/live cycles). Supply `{"bundle_artifact_id": "...", "mode": "live|replay", "dry_run": true|false, "workspace_id": "...", "approval_token": "...", "llm_config_id": "..."}`. Errors (missing bundle, invalid llm config) raise `404`, execution failures emit `500`.
* `GET /api/v1/runs/{run_id}` – Fetches the persisted `cycle_report.yaml` for that run. Runs are stored under `<workspace>/reports/runs/<run_id>`.

Both endpoints honor the workspace context just like the controller routes and share the same payloads so they can be consumed by tooling that relies on `/api/v1`.
