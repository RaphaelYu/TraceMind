# Controller Studio UI Reference

Controller Studio v0 is the wizard-style front end for running tm-controller cycles entirely over HTTP. It assumes a running `tm-server` instance and follows the seven-page workflow described in `TODOs/codex/T46_ui_controller_studio.yaml`.

## tm-server integration

- The UI talks exclusively to `tm-server` using the `/api/v1/workspaces` and `/api/controller` endpoints documented in `docs/tm_server_api.md`.
- No artifacts or policies are written by the UI itself—every approved cycle and replay is routed through tm-server, which persists accepted artifacts, registry entries, reports, gap maps, and backlog files under the mounted workspace.
- Set the `VITE_TM_SERVER_URL` environment variable before running the dev server or build to point the UI at your tm-server host (default: `http://localhost:8600`).

## LLM config registry

- Step 2 now uses `/api/v1/llm/prompt-templates` to discover available decide templates and `/api/v1/llm/configs` to list or create saved model + prompt combinations scoped to the active workspace.
- Create a registry entry once via `POST /api/v1/llm/configs` and reuse its `config_id` when running cycles so tm-server records the exact model, prompt template version, and optional prompt hash (plus provider details) for every run.
- When you submit a cycle request (`/api/controller/cycle`), the UI sends `llm_config_id`. The resulting report payload now contains `llm_config_id` and `llm_config` details, and `ProposedChangePlan@v0` writes the recorded `config_id`/`prompt_version` inside `llm_metadata`.

## Wizard flow

1. **Select bundle** – mount or select a workspace, then pick an accepted controller bundle from the tm-server registry. The UI displays workspace metadata (languages, directories) alongside bundle details.
2. **Configure LLM** – select or create a saved config (model + prompt template version) so tm-server stores a reproducible `llm_config_id`. The metadata auto-populates after previewing a cycle, and the recorded config is referenced for every subsequent run.
3. **Run live cycle** – trigger a preview (dry run) cycle. tm-server executes the Observe→Decide→Act workflow, records the artifacts, and returns the generated run ID plus report payload.
4. **Review plan diff** – the Plan Review pane surfaces each effect operation (target, params, idempotency key, rollback hint) alongside a JSON diff and execution evidence. The Policy Panel explains every guard decision so reviewers understand why a resource effect was approved or denied before acting.
5. **Approve & act** – after you explicitly mark the plan as approved, the UI generates an `approval_token` (prefixed with `approved-…`) and sends it with the POST to `/api/controller/cycle`. tm-server stores this token in the run context and refuses to run the Act stage when resource effects exist unless the token is present. With approval granted, tm-server commits the controller artifacts and run report.
6. **Report timeline** – browse tm-server’s persisted run history, including run IDs, durations, statuses, and associated backlogs or gap maps.
7. **Replay** – select a prior report and replay it with a new run ID. tm-server honors the deterministic artifacts and does not re-invoke the LLM; it simply replays the approved plan and records the fresh report.

## Artifact editing

- The header now includes an **Artifacts** view that sits alongside the wizard. It exposes Intents and Bundles tabs backed by `/api/v1/artifacts`, so you can create/update artifacts without hand-editing YAML.
- Each tab loads the registry entries for the active workspace, opens the selected artifact in a form, and surfaces validation errors returned by the server.
- See `docs/ui_artifact_editing.md` for the new workflow and form field mapping.

## Surface data

- **Snapshot hash**: retrieved from the `EnvSnapshot@v0` artifact stored under the workspace’s `.tracemind` directory.
- **Plan hash / ID**: shown from the `ProposedChangePlan@v0` body so reviewers can verify determinism.
- **Policy decisions**: the report payload lists each guard decision (allowed/denied with reasons) recorded by `PolicyGuard`.
- **Evidence summary**: the ExecutionReport artifact contains bundled evidence from the Observe, Decide, and Act agents; the UI surfaces per-agent entries.
- **Diff views**: a JSON diff table highlights every added, removed, or modified field between the snapshot and the proposed plan.

## Replay timeline

- The timeline section lists all reports under `<workspace>/reports/runs`. Selecting an entry allows you to replay it; the UI issues `/api/controller/cycle` with a `run_id` prefixed by `replay-` so stored artifacts are reproducible and audit-friendly.
- Replay results append to the timeline as new runs; gaps/backlogs issued during replay are preserved by tm-server.

## Running the UI

1. `cd ui/controller-studio`
2. `npm install`
3. `VITE_TM_SERVER_URL=http://localhost:8600 npm run dev -- --host`

For production builds, run `npm run build`. The bundler compiles the wizard into static assets that still require tm-server to operate.
