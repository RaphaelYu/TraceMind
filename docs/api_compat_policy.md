# TraceMind TM server API compatibility policy (v1)

This policy codifies what is allowed once `/api/v1` is considered stable. Follow it when changing any controller server code that touches the v1 surface.

## Scope

- The `/api/v1` prefix is the **stable contract** exposed to clients (Controller Studio, automation, integrations).
- Anything outside `/api/v1` (legacy controller routes, demos, CLI endpoints) can evolve more freely, but stable clients must never filter for them as “supported”.
- Policy changes and documentation updates must land alongside code so clients can detect deprecations without guesswork.

## Allowed changes within v1

1. **Additive responses** – you may add new fields/objects to response payloads as long as they are optional additions.
2. **Optional request fields** – new request properties must be optional so existing clients keep sending the same body.
3. **Documentation-only deprecations** – mark deprecated behaviors in docs and optionally emit an `X-TM-Deprecated` response header or `meta.deprecations` list before removing support in a future major version.

## Prohibited breaking changes

- Removing fields/objects from responses or changing their data type.
- Changing the semantic meaning of the core HTTP status codes 400, 401, 403, 404, 409, or 422 for existing endpoints.
- Moving `/api/v1` clients to a new base path without releasing an accompanying v2 prefix.
- Switching from synchronous to asynchronous responses, changing wire format (JSON → YAML), or increasing required request fields.

## Version bumps and deprecations

- Any change that violates the policy above requires a new major prefix (e.g., `/api/v2`). Keep the previous version running during the transition.
- Document deprecations in `docs/api_compat_policy.md` and highlight new headers/fields that signal deprecated behavior.
- If you introduce `X-TM-Deprecated`, explain the expected lifetime, the replacement path, and when it will be removed.

## Validation

- Update the contract tests in `tests/test_api_contract_v1.py` whenever you change `/api/v1`. The tests ensure every mandatory field and status code is still present.
- Use the OpenAPI snapshot (`docs/openapi_v1.json`) to keep ABI tracking in sync with the code.
