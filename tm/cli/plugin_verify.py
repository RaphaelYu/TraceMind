from __future__ import annotations

import sys

from tm.plugins.loader import PluginError, load


def _is_exporter(plugin: object) -> bool:
    required = ("setup", "on_event", "flush", "teardown")
    return all(callable(getattr(plugin, attr, None)) for attr in required)


def verify(group: str, name: str) -> int:
    try:
        plugin = load(group, name)
    except PluginError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - unexpected loader failure
        print(f"failed to load plugin: {exc}", file=sys.stderr)
        return 2

    if not _is_exporter(plugin):
        print(f"unsupported plugin type: {type(plugin).__name__}", file=sys.stderr)
        return 2

    try:
        plugin.setup({})
        plugin.on_event({"ping": True})
        plugin.flush()
    except Exception as exc:
        print(f"plugin raised: {exc}", file=sys.stderr)
        try:
            plugin.teardown()
        except Exception:
            pass
        return 2

    try:
        plugin.teardown()
    except Exception as exc:
        print(f"plugin teardown failed: {exc}", file=sys.stderr)
        return 2

    print(f"OK: {group}:{name}")
    return 0


def run(args) -> None:
    code = verify(args.group, args.name)
    if code:
        sys.exit(code)
