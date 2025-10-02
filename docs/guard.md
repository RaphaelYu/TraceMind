# Guardrails

Guardrails provide input/output filtering before flows run or within a recipe step.

## Built-in Rules

| Rule | Parameters | Description |
| ---- | ---------- | ----------- |
| `length_max` | `path`, `value` | Reject if string length exceeds `value`. |
| `required` | `path` | Reject when the path is missing or empty. |
| `regex_deny` | `path`, `pattern`, `ignore_case` | Reject when the regex matches. |
| `deny_keywords` | `path`, `values` | Reject when any keyword appears (case-insensitive). |

Rules are defined with JSON-style paths (`$.input.text`, `$.items[*].name`).

## Configured Guards

`trace-mind.toml` can register global, per-flow, or per-policy-arm rules.

```toml
[governance.guard]
enabled = true

[[governance.guard.rules]]
scope = "global"
rules = [
  { type = "deny_keywords", path = "$.input.prompt", values = ["DROP TABLE", "rm -rf"] }
]

[[governance.guard.rules]]
scope = "flow"
target = "sensitive_flow"
rules = [
  { type = "length_max", path = "$.input.summary", value = 2000 }
]
```

Request guards run before a job is queued and return `error_code="GUARD_BLOCKED"` when violated.

## `helpers.guard` Step

Inside a recipe, add a guard step:

```yaml
steps:
  - id: validate
    type: helpers.guard
    rules:
      - type: required
        path: $.state.ticket_id
      - type: regex_deny
        path: $.state.message
        pattern: "(?i)(?:ssn|social security)"
```

A violation raises `GuardBlockedError`, producing a flow result with `error_code="GUARD_BLOCKED"` alongside the offending rule metadata.

## Custom Hooks

Register project-specific rules:

```python
from tm.guard import register_guard, GuardViolation

@register_guard("flag_sensitive")
def deny(ctx, values, meta):
    for idx, value in enumerate(values):
        if isinstance(value, str) and value.count("secret") > 2:
            yield GuardViolation(
                rule="flag_sensitive",
                path=meta.get("path"),
                reason="too_many_secrets",
                details=(("index", idx),)
            )
```

Then reference the rule in recipes or config (`type="flag_sensitive"`).
