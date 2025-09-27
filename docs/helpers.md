# Helpers Reference

TraceMind ships a small `tm.helpers` module with pre-built building blocks for
flow steps and common data operations. All helpers are pure Python and can be
used directly in recipes or regular Flow definitions.

## 1. Execution Helpers

### 1.1 `switch`

Selects a branch label for `SWITCH` steps. Signature (async):

```python
await switch(ctx, state, selector=None, cases=None, default=None)
```

* `selector` – callable or dotted string resolving to `callable(ctx, state)`.
  If omitted, the helper looks for `state["branch"]`.
* `cases` / `default` – optional dictionary matching branch labels to edge ids.
  When omitted, the helper reads `ctx["config"]["cases"]` / `ctx["config"]["default"]`.

**Example**

```python
import asyncio
from tm.helpers import switch

ctx = {"config": {"cases": {"manual": "manual", "auto": "auto"}, "default": "auto"}}
state = {"branch": "manual"}
label = asyncio.run(switch(ctx, state))
# label == "manual"
```

### 1.2 `when`

Evaluates a predicate for conditional routing. Signature:

```python
await when(ctx, state, predicate=None)
```

If `predicate` is omitted the helper returns `bool(state)`.

### 1.3 `parallel`

Runs several branches concurrently and merges results. Signature:

```python
await parallel(ctx, state, branches=None)
```

* `branches` – mapping of branch name → callable (or dotted string). When not
  provided the helper expects `ctx["config"]["branches_map"]`.
* Returned value – merged dictionary; mapping outputs are deep-merged following
  the `deep_merge` semantics, other values are placed under their branch name.

**Example**

```python
import asyncio
from tm.helpers import parallel

async def branch_a(ctx, state):
    return {"text": state.get("document", "").upper()}

def branch_b(ctx, state):
    return {"label": "ok"}

ctx = {"config": {"branches_map": {"a": branch_a, "b": branch_b}}}
result = asyncio.run(parallel(ctx, {"document": "hello"}))
# result == {"text": "HELLO", "label": "ok"}
```

## 2. I/O Helpers

| Helper | Description | Notes |
| --- | --- | --- |
| `load_json(path_or_text)` | Deserialize JSON from a file path or raw string. | Accepts `Path` or `str`. |
| `dump_json(data, indent=2)` | Serialize to JSON text with UTF-8 safe characters. | Returns `str`. |
| `load_yaml(path_or_text)` | Load YAML from path or text. | Requires `PyYAML` (`pip install PyYAML`). |

Example:

```python
from tm.helpers import load_json, dump_json

data = load_json("config/example.json")
print(dump_json(data, indent=4))
```

## 3. Patch Helpers

### 3.1 `deep_merge`

```python
deep_merge(base, overlay, array_mode="replace")
```

* Merges mappings recursively, cloning inputs.
* Lists are replaced by default; set `array_mode="concat"` to append.
* Non-collection values are replaced.

### 3.2 `json_patch_diff` / `json_patch_apply`

Implements RFC 6902 (JSON Patch) for simple structures. Diff emits a list of
`{"op", "path", "value"}` operations; apply executes them against a document.

### 3.3 `json_merge_patch`

Implements RFC 7386 (JSON Merge Patch). `None` removes keys; nested objects are
merged recursively.

**Patch Behavior Summary**

| Scenario | `deep_merge` | `json_patch_diff/apply` | `json_merge_patch` |
| --- | --- | --- | --- |
| Object + Object | Recursively merged; new keys added. | Diff emits `add`/`remove`/`replace`. | Follow patch document; `None` deletes. |
| List + List | `replace` or `concat` per `array_mode`. | Lists compared; replaced when unequal. | Entire list replaced. |
| Primitive + Primitive | Replaced with overlay. | `replace` op emitted. | Replaced with patch value. |

**Round-trip Example**

```python
from tm.helpers import deep_merge, json_patch_diff, json_patch_apply, json_merge_patch

base = {"profile": {"name": "Ada", "tags": ["alpha"]}}
overlay = {"profile": {"tags": ["beta", "gamma"], "active": True}}
merged = deep_merge(base, overlay)
# merged == {"profile": {"name": "Ada", "tags": ["beta", "gamma"], "active": True}}

patch = json_patch_diff(base, merged)
restored = json_patch_apply(base, patch)
# restored == merged

merge_patch = {"profile": {"tags": None, "score": 10}}
patched = json_merge_patch(merged, merge_patch)
# patched == {"profile": {"name": "Ada", "active": True, "score": 10}}
```

All snippets above run as-is. Be sure to install `PyYAML` if you plan to call
`load_yaml`.
