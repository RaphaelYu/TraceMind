# Storage Guide

TraceMind persists routine agent state (task queues, knowledge store, etc.) on disk so that runs survive process restarts.  This guide explains how the Knowledge Store (KStore) works, how to select a driver, and how to verify that persistence is working on your machine.

## KStore overview

The KStore is a simple key/value registry used by subsystems such as the Recorder, the queue supervisor, and validation tooling.  Drivers are discovered through a registry in `tm.kstore`:

| URL scheme | Description                                    | Notes |
|------------|------------------------------------------------|-------|
| `jsonl://` | Portable append-only JSON Lines file           | Default on every platform |
| `sqlite://`| SQLite-backed store (WAL mode, retry tolerant) | Enabled automatically when `sqlite3` is importable |

If a driver cannot be loaded, the registry falls back to a local JSON Lines file so that CLI commands still run without additional setup.

```bash
# Default path when no URL is specified
echo "${TM_KSTORE:-jsonl://./state.jsonl}"
```

## Selecting a driver

Set the `TM_KSTORE` environment variable before launching the CLI or embedding the runtime.  The examples below are safe to copy/paste on macOS, Linux, or Windows shells.

```bash
# 1. Use a dedicated JSONL file in ./tmp/demo-state.jsonl
TM_KSTORE="jsonl://./tmp/demo-state.jsonl" tm run templates/minimal/flows/hello.yaml -i '{"name":"TraceMind"}'

# 2. Use SQLite with an explicit filename (requires sqlite3 to be installed)
TM_KSTORE="sqlite://./tmp/demo-state.db" tm run templates/minimal/flows/hello.yaml -i '{"name":"TraceMind"}'
```

Whenever the runtime opens a store it prints nothing by default.  You can confirm the correct driver is being used by checking the newly created file:

```bash
ls -lh tmp/demo-state.*
```

## Optional: programmatic access

`tm.kstore.open_kstore()` resolves a URL and returns the appropriate driver.  The example below writes and reads a record using the same logic as the CLI.

```bash
python3 - <<'PY'
from tm.kstore import open_kstore, DEFAULT_KSTORE_URL

store = open_kstore(DEFAULT_KSTORE_URL)
store.put("demo:item", {"note": "hello from docs"})
print("stored:", store.get("demo:item"))
store.delete("demo:item")
store.close()
PY
```

## Fallback behaviour

- `NO_SQLITE=1` forces the registry to skip the SQLite driver.  This is how the CI “no-sqlite” job verifies the JSONL path.
- Missing directories are created automatically.  Ensure the process has write permissions to the destination folder.
- Corrupt records trigger a best-effort rollback.  JSONL writes are atomic: the driver writes to a `*.tmp-<uuid>` file and then replaces the destination file once the flush completes.

## Troubleshooting

| Symptom | Cause & Fix |
|---------|-------------|
| `RuntimeError: jsonl driver not registered` | The `tm.kstore.jsonl` module could not import.  Reinstall the package or run `pip install trace-mind[yaml]` to pull optional deps. |
| `sqlite3.OperationalError: database is locked` | Another process is holding the SQLite file.  Either disable SQLite (`TM_KSTORE` → jsonl) or move the store to a location that supports file locking (local disk instead of network share). |
| Empty output even though a driver was selected | Verify that `TM_KSTORE` contains a valid URL (including scheme) and that the path is writable.  JSONL URLs must include a filename, e.g. `jsonl://./data/state.jsonl`. |

Need more detail?  See the implementation in `tm/kstore/jsonl.py` and `tm/kstore/sqlite.py`, or open a discussion in the repository.
