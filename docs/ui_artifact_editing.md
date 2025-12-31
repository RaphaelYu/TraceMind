# Controller Studio artifact editing

Controller Studio now exposes a dedicated **Artifacts** page right next to the controller wizard. It lets you browse existing Intents/Bundles and author new ones with structured forms instead of raw YAML.

## Workflow

1. Select a workspace (and accepted bundle) in the wizard, then switch the view toggle in the header to **Artifacts**.
2. Choose the **Intents** or **Bundles** tab to list the corresponding artifacts registered in the workspace.
3. Click an artifact to load its body for editing, or hit **New** to start from a blank form.
4. Update the form fields and click **Create artifact** / **Save changes**. The UI sends just `artifact_type` + `body` to `/api/v1/artifacts`; tm-server constructs the envelope, verifies it, writes the accepted document under `workspace/specs/…`, and refreshes the registry.
5. Validation failures return structured errors that appear above the form. Success shows the saved artifact ID and reloads the list automatically.

## Forms

- **Intent editor**: captures intent_id, title, context, goal, actors, IO, constraints, and trace links. Array fields accept newline-separated values to keep the UI compact.
- **Bundle editor**: lets you add agents and plan steps. Each agent captures runtime metadata, IO refs, and effect targets, while each step records the agent reference plus inputs/outputs. Preconditions section feeds the bundle’s `meta.preconditions`.

## Server API

- `GET /api/v1/artifacts` lists all registry entries for the workspace.
- `GET /api/v1/artifacts/{artifact_id:path}` fetches the accepted document (supports IDs with slashes).
- `POST /api/v1/artifacts` / `PUT /api/v1/artifacts/{artifact_id:path}` create or update artifacts from the submitted body. tm-server accepts/verify, persists to `specs`, and updates `.tracemind/registry.jsonl`.

This replaces the need to edit artifacts manually in YAML or the CLI; the forms drive the same schema-backed validation that the verifier already enforces.
