# Controller Studio UI

This Vite + React app provides the Controller Studio wizard that lets you mount TraceMind workspaces, select verified bundles, preview plans, approve a controller cycle, follow the report history, and replay past runs without ever editing YAML or running the CLI.

## Setup

```bash
cd ui/controller-studio
npm install
```

## Development

```bash
VITE_TM_SERVER_URL=http://localhost:8600 npm run dev -- --host
```

The `VITE_TM_SERVER_URL` variable tells the UI where `tm-server` is running (default: `http://localhost:8600`). You can point the UI at any tm-server instance that exposes the `/api` endpoints described in `docs/tm_server_api.md`.

## Build

```bash
npm run build
```

## Features

- **Step-by-step wizard**: The UI walks through (1) selecting a bundle, (2) documenting LLM metadata, (3) running a preview cycle, (4) reviewing plan diffs, (5) approving and running the live cycle, (6) browsing the persisted report timeline, and (7) replaying previous reports.
- **LLM config registry**: Step 2 now lists available prompt templates plus saved configs via `/api/v1/llm`, so you can persist model + prompt template combinations and reuse their `config_id` on every run.
- **Artifact form editors**: Use the new Artifacts page to list, create, and update Intent + Controller bundle artifacts via `/api/v1/artifacts`; the forms drive the verifier-backed schema without YAML.
- **Surface data**: Snapshot hash, plan hash, policy decisions, execution evidence, and diff views are all pulled from the tm-server responses so you can audit each controller cycle.
- **tm-server driven**: Controller Studio never writes artifacts locally; it simply drives `tm-server`, which persists accepted artifacts, registry entries, reports, and replay records inside the workspace.
- **Effect review & policy explanation**: Step 4 highlights every effect’s target, parameters, idempotency key, rollback hint, and guard decision before you move on.
- **Explicit approval token**: Approving a plan produces an `approved-…` token that the UI submits alongside the live run request to keep tm-server from executing resource effects without your sign-off.

Read `docs/controller_studio.md` for a deeper description of the UI flow and how it maps to tm-server endpoints.
