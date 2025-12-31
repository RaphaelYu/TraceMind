# TraceMind TM Server API

For the stable `/api/v1` surface, see [docs/tm_server_api_v1.md](tm_server_api_v1.md) and the compatibility requirements described in [docs/api_compat_policy.md](api_compat_policy.md).

This HTTP service lets a UI or other automation drive TraceMind controller cycles without invoking the CLI. The server now works on TraceMind workspaces described by `tracemind.workspace.yaml`, which specify the workspace ID, directories, languages, and commit policy. That manifest identifies where the accepted registry lives (`.tracemind/registry.jsonl`) and where run reports, artifacts, and decide records are persisted (under the workspace's `reports` and `artifacts` folders). Legacy `TM_SERVER_*` environment variables still shape the default server config, but mounting a workspace overrides those paths for controller work.

## Running the server

```bash
source ./venv/bin/activate
uvicorn tm.server.app:app --host 0.0.0.0 --port 8600
```

Environment overrides (legacy server config):
- `TM_SERVER_DATA_DIR`: base directory for run state (`tm_server` by default).
- `TM_SERVER_REGISTRY_PATH`: explicit registry path if you keep it outside `.tracemind`.
- `TM_SERVER_RECORD_PATH`: path for controller decide records (defaults to `.tracemind/controller_decide_records.json`).

Controller runs land under `<workspace-root>/reports/runs/<run_id>` once you mount a workspace (controller artifacts live under `<workspace-root>/artifacts/controller_artifacts/<run_id>`), but if you rely on the base server config without a workspace the legacy `TM_SERVER_DATA_DIR/runs/<run_id>` directory still hosts the generated `cycle_report.yaml`, `gap_map.yaml`, `backlog.yaml`, and `controller_artifacts/` folder.

## Workspaces

The controller server now scopes registry, artifacts, and reports inside a TraceMind workspace described by `tracemind.workspace.yaml`. Each manifest must declare `workspace_id` and `name` and can optionally override directories (`specs`, `artifacts`, `reports`, `prompts`, `policies`), specify a `commit_policy` (required/optional globs), and enumerate supported `languages`. Mount a workspace via `/api/v1/workspaces/mount` before invoking controller operations so the server knows where to load accepted artifacts, persist run reports, and place gap/backlog files.

### Workspace endpoints

- `POST /api/v1/workspaces/mount` – body `{"path": "<workspace-root>/tracemind.workspace.yaml"}` loads the manifest and returns a descriptor containing the resolved directories, commit policy, languages, and workspace ID.
- `GET /api/v1/workspaces` – list the currently mounted workspaces.
- `GET /api/v1/workspaces/current` – inspect the selected workspace (returns `null` if none).
- `POST /api/v1/workspaces/select` – body `{"workspace_id": "..."}:` change the active workspace.

### `POST /api/v1/workspaces/init`

Create a runnable workspace in one shot. Provide the root path and a name, and the API writes:

1. `tracemind.workspace.yaml` with the requested name/ID (a slug-derived workspace ID is used when omitted), directories, languages, and commit policy.
2. A minimal controller bundle (`specs/controller_bundle.yaml`) plus an intent template (`specs/intents/example_intent.yaml`) so you can immediately register and run the demo controller.
3. An optional `.gitignore` update (controlled by the `append_gitignore` flag) that appends the snippet stored in `specs/templates/workspace_gitignore.txt`.

The response returns the manifest path, resolved directories, the generated sample files, and the gitignore snippet so UIs can display or download it.

When a workspace is selected, controller endpoints honor the optional `workspace_id` query parameter to scope registry lookups, artifact retrieval, and run directories. If omitted, the API defaults to the active workspace.

## API reference

Controller endpoints run against a mounted workspace. Supply the optional `workspace_id` query parameter to scope registry, artifacts, and reports to a specific workspace; if it is omitted the API uses the currently selected workspace.

### `GET /api/controller/bundles`
Lists accepted agent bundle artifacts from the registry. Returns the registry entry (artifact ID, intent ID, artifact path, metadata, etc.).

### `POST /api/controller/cycle`
Kicks off a single controller cycle.

Request payload:

```json
{
  "bundle_artifact_id": "tm-controller/demo/bundle",
  "mode": "live",
  "dry_run": false,
  "run_id": "optional-custom-id",
  "approval_token": "approved-20240101T000000Z",
  "llm_config_id": "llm-config-01a2b3c4"
}
```

When `dry_run` is `false` and the proposed plan contains any `resource:` effects, the controller server requires an `approval_token` that begins with `approved`. This token is recorded inside the run context so auditors can trace the approval for resource changes. Preview cycles (`dry_run: true`) bypass approval enforcement but still surface the same report payload so you can inspect the plan before approving.

Response includes the generated `run_id`, the `cycle_report` that was persisted, any emitted `gap_map`/`backlog`, the chosen `approval_token` (if present), and the inlined report payload.

The JSON response now also exposes `llm_config_id` plus an `llm_config` object mirroring the registered config so clients can present the chosen model/prompt information. The persisted report and `ProposedChangePlan@v0` artifact update their `llm_metadata` with `config_id` and `prompt_version` so every downstream consumer can prove which prompt template and fingerprint drove the run.

Runs always reuse the accepted artifact stored on disk (`bundle_artifact_id` must exist in the registry) and ship the controller decide records at `TM_SERVER_RECORD_PATH`, ensuring every execution is reproducible.

Include `workspace_id` as a query parameter (or rely on the selected workspace) so the controller knows which workspace registry and directories to use. The run report is persisted under `<workspace>/reports/runs/<run_id>`, the gap/backlog documents end up under that workspace's reports directory, and controller artifacts land inside `<workspace>/artifacts/controller_artifacts/<run_id>`.

### `GET /api/v1/llm/prompt-templates`
Returns every prompt template version baked into the controller (`tm/controllers/decide/prompt_templates/*.md`). Each entry includes the parsed `version`, a `title`, and optional `description` so clients can describe the choices users have before they create a config.

### `GET /api/v1/llm/configs`
Lists saved model + prompt template combinations for the workspace. Supply the optional `workspace_id` query parameter to scope the lookup; if omitted, the active workspace is used. Each entry contains the assigned `config_id`, `model`, `prompt_template_version`, `prompt_version`, optional `model_id`/`model_version`, and the `created_at` timestamp.

### `POST /api/v1/llm/configs`
Create a registry entry by POSTing metadata such as:

```json
{
  "model": "gpt-4.1",
  "prompt_template_version": "v0",
  "prompt_version": "controller-20240101",
  "model_id": "openai-gpt-4.1",
  "model_version": "4.1-full"
}
```

`prompt_version`, `model_id`, and `model_version` are optional. The controller validates that the requested `prompt_template_version` exists under `tm/controllers/decide/prompt_templates`; submissions with unknown versions return `400 Bad Request`. Accepted configs are appended to `<workspace>/artifacts/llm_configs.jsonl` and returned with an assigned `config_id` and `created_at`.

The saved `config_id` is referenced in `/api/controller/cycle` requests so the decide agent knows which model/prompt to execute, and the run artifacts store the recorded metadata alongside the plan's `llm_metadata`.

### `GET /api/controller/reports`
Returns summaries for all completed runs (each entry contains the run ID, report payload, report path, and any gap/backlog documents).

### `GET /api/controller/reports/{run_id}`
Fetches the raw report document (`cycle_report.yaml`) for the given `run_id`.

### `GET /api/controller/artifacts`
Filters the registry by `intent_id`, `body_hash`, or `artifact_type`. If no query parameters are provided, it returns all entries.

### `GET /api/controller/artifacts/{artifact_id}`
Returns the registry entry plus the stored artifact document (YAML/JSON) for the matching artifact ID.

### `POST /api/controller/artifacts/diff`
Computes a JSON diff between two registry artifacts. Request payload:

```json
{
  "base_id": "tm-controller/env_snapshot-controller-demo",
  "compare_id": "tm-controller/env_snapshot-prev"
}
```

The response lists each difference, showing the path, operation (`added`/`removed`/`modified`), and the differing values.

### Workspace artifact editing API

- `GET /api/v1/artifacts` – lists accepted artifacts registered for the workspace. Supply `workspace_id` to scope the query (or rely on the selected workspace) and optionally filter by `artifact_type=intent` or `artifact_type=agent_bundle`. Each entry includes the registry metadata (artifact ID, body hash, status, path, etc.).
- `GET /api/v1/artifacts/{artifact_id:path}` – fetches the registry entry plus the stored YAML document for the matching artifact. The `{artifact_id}` segment supports nested IDs (slashes), so clients can reload bundles or intents that use hierarchical identifiers.
- `POST /api/v1/artifacts` – create a new intent or agent bundle by POSTing `{"artifact_type": "...", "body": {...}}`. The server derives the artifact ID from `intent_id` or `bundle_id`, constructs a candidate envelope, runs `verify()`, writes the accepted artifact under `<workspace>/specs/{artifact_type}/...`, updates the registry (`.tracemind/registry.jsonl`), and returns the stored envelope/body. Provide `workspace_id` as a query parameter (or rely on the selected workspace).
- `PUT /api/v1/artifacts/{artifact_id:path}` – update an existing artifact using the same payload shape. The route rewrites the accepted artifact file, re-runs accept/verify, and rewrites the registry entry so the workspace’s specs folder remains the source of truth.
