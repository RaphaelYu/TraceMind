# TM-SPEC-WORKSPACE-REPO-V0

## Overview

`TM-SPEC-WORKSPACE-REPO-V0` defines the durable workspace and repository contract for HTTP‑first TraceMind installs. A workspace is a directory tree that surfaces a manifest, standard data folders, verified artifacts, and optionally drivers in other languages. This spec ensures automation can discover workspaces, resolve canonical paths, and make safe git decisions without ad hoc configuration.

## Workspace manifest

The workspace manifest is `tracemind.workspace.yaml` at the workspace root. It describes the workspace identity, directory overrides, and the policies required for a workspace to run controller cycles.

### Required fields

| Field | Description |
| --- | --- |
| `workspace_id` (string) | Unique workspace identifier (DNS-style) used for HTTP endpoints and storage isolation. |
| `name` (string) | Human-readable name displayed in UI and logs. |
| `root` (string) | Relative path (default `.`) that anchors workspace paths. |
| `directories` (mapping) | Optional overrides for the default directories (see below). |
| `commit_policy` (mapping) | Describes which artifact classes must be committed vs ignored (see section below). |
| `languages` (sequence of strings) | Declares coexisting runtimes (e.g., `python`, `rust`, `bash`) for UI/runtime awareness. |

### Example manifest

```yaml
workspace_id: "trace-mind:///example"
name: "Example workspace"
root: "."
directories:
  specs: "specs"
  artifacts: ".tracemind"
  reports: "reports"
  prompts: "prompts"
  policies: "policies"
commit_policy:
  required:
    - "specs/**/*.yaml"
    - "accepted/**/*.yaml"
  optional:
    - "prompts/**/*"
languages:
  - python
  - rust
```

## Default directories

Unless overridden in `directories`, workspaces expose:

| Logical role | Default path (relative to manifest `root`) | Notes |
| --- | --- | --- |
| `specs` | `specs/` | Intent/controller bundle specs, policy drafts, and templates. |
| `artifacts` | `.tracemind/` | Verifier outputs, registry, run reports, decide records; _not_ committed by default. |
| `reports` | `reports/` | Human-readable summaries, CI tickets, or audit logs. |
| `prompts` | `prompts/` | Reusable prompt templates, toolkits, or system messages. |
| `policies` | `policies/` | Policy specs, allow lists, and compliance rules. |

Workspaces may preserve additional directories (e.g., `data/`, `fixtures/`, language-specific folders), but they must be declared via the manifest or kept outside workspace `root`.

## Commit policy

A deterministic commit policy helps UI/drivers and automation understand what belongs in version control:

1. **Required commits** (tracked by `commit_policy.required`):
   * `specs/` artifacts that define intents, controller bundles, or driver-facing contracts.
   * `accepted/` artifacts produced by the verifier that confirm controller readiness.
   * Policy specifications referenced by pipelines.
2. **Optional commits** (tracked by `commit_policy.optional`):
   * `prompts/` material or doc artifacts.
   * Workspace templates and examples under `specs/templates/`.
3. **Never commit**:
   * `.tracemind/` outputs, run reports, and decide records unless a workspace specifically overrides `artifacts` to a tracked tree and explicitly whitelists it.
* Secrets, API keys, and runtime caches (see `tm/security/secrets.py` once implemented). Workspaces may keep a unlockable secrets file under `.tracemind/secrets.yaml`; the server provides helpers to read/register values per workspace without committing the file.

Commit policy entries support glob syntax; servers and UI clients should highlight diffs that touch required sets.

## Multi-language expectations

TraceMind workspaces may host non-Python drivers (Rust, Go, etc.):

* Drivers must respect the same spec directories and git policy; they locate manifests by walking up the filesystem until `tracemind.workspace.yaml` is found.
* Language bindings communicate over HTTP (`tm/server` APIs) and only rely on accepted artifacts and run reports; they do not access workspace internals directly.
* Artifact producers (Python or otherwise) must surface metadata (e.g., `workspace_id`, `language`, `driver_version`) in the manifest or manifest-adjacent files so the UI can display the correct driver for the workspace.

## HTTP-first workflow alignment

The workspace contract supports HTTP-first interactions:

* `tm-server` GET/POST APIs mount a workspace by reading `tracemind.workspace.yaml` and use the resolved directories to read/write specs, reports, and controller outcomes.
* Workspace IDs appear in HTTP responses (`/api/v1/workspaces`, `/api/controller/...`) so clients have a stable reference for multi-workspace sessions.
* Repository status endpoints rely on the commit policy to compute “suggested commit sets” for controller specs while ignoring runtime artifacts.

## Acceptance criteria

* The spec names a single manifest (`tracemind.workspace.yaml`) with required fields, default directories, and optional overrides.
* Commit rules are explicit about what must be committed, what may be optional, and what is never committed.
* Multi-language expectations explain how Rust/other drivers find the workspace and interact over HTTP.
* The spec explicitly mentions that TM server workflows rely on these paths, matching the HTTP-first objective.
