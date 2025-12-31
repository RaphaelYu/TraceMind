# HTTP connector schema v0

TraceMind's HTTP connector agent (`tm-agent/controller-http:0.1`) lets controller runs apply safe HTTP resource effects under policy guard supervision. The connector expects every decision to describe a deterministic HTTP call via `target_state` and enforces workspace-local allowlists plus idempotency guards.

## Agent inputs

- `state:env.snapshot` — the environment snapshot that seeded the controller loop (used for reporting and idempotency correlation).
- `artifact:proposed.plan` — the proposed change plan containing `decisions` that the HTTP connector executes.

## Decision schema (`target_state`)

Each decision's `target_state` must follow this schema:

| Field | Type | Description |
| --- | --- | --- |
| `method` | `string` | HTTP method (`GET`, `POST`, `PUT`, or `PATCH`). Defaults to `GET`. |
| `url` | `string` | Full target URL (scheme + host + path + optional query). |
| `headers` | `object` | Optional request headers. The connector adds `Content-Type` or `Idempotency-Key` when required. |
| `params` | `object` | Optional query parameters (name→value). These are merged with any query already present in `url`. |
| `body` | `string`/`object` | Optional payload. Objects are serialized as JSON. |
| `allowlist_key` | `string` | Required key that selects the allowlist entry from agent config. |
| `idempotency_key` | `string` | Optional idempotency identifier; when provided and the method is not `GET`/`HEAD`, the connector sets the `Idempotency-Key` header so downstream HTTP services can deduplicate writes. |

The connector also respects `decision.idempotency_key` for reporting and policy decisions.

## Agent configuration

The agent configuration (`config_schema`) exposes:

```json
{
  "allowlist": [
    {
      "name": "string",
      "url_prefix": "string",
      "methods": ["GET", "POST", "PUT", "PATCH"]
    }
  ],
  "timeout_seconds": 30.0
}
```

- `allowlist`: list of named targets. Each entry restricts requests to URLs that start with `url_prefix` and to the listed HTTP methods.
- `timeout_seconds`: optional socket timeout (seconds) for each request (default `30`).

Every `target_state` must reference a defined `allowlist_key`; requests outside the configured prefix or method set fail before talking to the network.

## Evidence and outputs

- The agent writes `artifact:execution.report` plus `state:act.result` just like the built-in actor.
- Each HTTP call also emits `builtin.http_connector` evidence records with:
  - `effect_ref`, `method`, `url`
  - `request_fingerprint` (method + canonicalized path + sorted query names; no secrets)
  - `status`, `response_hash` (SHA-256 of the body)
  - `response_snippet` (first 512 characters of the UTF-8–decoded body)
  - `allowlist` entry name and `idempotency_key` (when provided)

Responses are not stored verbatim; the connector only keeps the fingerprint, status, hash, and snippet so the run report can prove what was requested without leaking secrets.

## Runtime behavior

1. The HTTP connector iterates `plan.decisions`.
2. For each decision it builds the final URL, enforces the allowlist, adds `Idempotency-Key` for unsafe methods, and issues the request via `urllib.request`.
3. Successful requests update the `artifact_refs` map and the execution report; failures become `errors` entries and deny policy decisions so reviewers can inspect why the effect was rejected.
4. The connector leaves snapshots and reports deterministic so rerunning the bundle with the same plan never replays a different HTTP call (the idempotency key plus allowlist ensure replay safety).
