# TraceMind TM Server API

This HTTP service lets a UI or other automation drive TraceMind controller cycles without invoking the CLI. The server relies on accepted artifacts stored in the registry (`.tracemind/registry.jsonl`) and records run reports, controller artifacts, and decide records inside `tm_server` by default (customize via `TM_SERVER_DATA_DIR`).

## Running the server

```bash
source ./venv/bin/activate
uvicorn tm.server.app:app --host 0.0.0.0 --port 8600
```

Environment overrides:
- `TM_SERVER_DATA_DIR`: base directory for run state (`tm_server` by default).
- `TM_SERVER_REGISTRY_PATH`: explicit registry path if you keep it outside `.tracemind`.
- `TM_SERVER_RECORD_PATH`: path for controller decide records (defaults to `.tracemind/controller_decide_records.json`).

Controller runs live inside `TM_SERVER_DATA_DIR/runs/<run_id>` so you can inspect the generated `cycle_report.yaml`, `gap_map.yaml`, `backlog.yaml`, and `controller_artifacts/` folder for each execution.

## API reference

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
  "run_id": "optional-custom-id"
}
```

Response includes the generated `run_id`, the `cycle_report` that was persisted, any emitted `gap_map`/`backlog`, and the inlined report payload.

Runs always reuse the accepted artifact stored on disk (`bundle_artifact_id` must exist in the registry) and ship the controller decide records at `TM_SERVER_RECORD_PATH`, ensuring every execution is reproducible.

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
