from __future__ import annotations

import argparse
import json
import sys
from argparse import _SubParsersAction
from pathlib import Path
from typing import Any, Mapping

from tm.utils.yaml import import_yaml

from tm.artifacts import ArtifactValidationError, validate_capability_spec
from tm.caps import CapabilityAlreadyExists, CapabilityCatalog, CapabilityNotFound

yaml = import_yaml()


def register_caps_commands(subparsers: _SubParsersAction) -> None:
    caps_parser = subparsers.add_parser("caps", help="manage capability catalog")
    sub = caps_parser.add_subparsers(dest="caps_cmd")

    register_parser = sub.add_parser("register", help="register a capability spec")
    register_parser.add_argument("spec", help="Path to capability YAML/JSON")
    register_parser.add_argument("--catalog", help="Catalog file path (default: ~/.trace-mind/capabilities.json)")
    register_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing capability")
    register_parser.set_defaults(func=_cmd_caps_register)

    list_parser = sub.add_parser("list", help="list registered capabilities")
    list_parser.add_argument("--catalog", help="Catalog file path (default: ~/.trace-mind/capabilities.json)")
    list_parser.set_defaults(func=_cmd_caps_list)

    show_parser = sub.add_parser("show", help="show a registered capability spec")
    show_parser.add_argument("--catalog", help="Catalog file path (default: ~/.trace-mind/capabilities.json)")
    show_parser.add_argument("capability_id", help="Capability identifier")
    show_parser.set_defaults(func=_cmd_caps_show)

    validate_parser = sub.add_parser("validate", help="validate a capability spec file")
    validate_parser.add_argument("spec", help="Path to capability YAML/JSON")
    validate_parser.set_defaults(func=_cmd_caps_validate)


def _load_structured(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read this file")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: expected mapping at top level")
    return data


def _resolve_catalog_path(arg: str | None) -> Path | None:
    if arg:
        return Path(arg)
    return None


def _cmd_caps_register(args: argparse.Namespace) -> None:
    path = Path(args.spec)
    try:
        payload = _load_structured(path)
    except Exception as exc:
        print(f"caps register: failed to load spec: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        validate_capability_spec(payload)
    except ArtifactValidationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

    catalog = CapabilityCatalog(path=_resolve_catalog_path(args.catalog))
    try:
        entry = catalog.register(payload, overwrite=args.overwrite)
    except CapabilityAlreadyExists as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

    print(f"registered capability: {entry.capability_id}")


def _cmd_caps_list(args: argparse.Namespace) -> None:
    catalog = CapabilityCatalog(path=_resolve_catalog_path(args.catalog))
    entries = catalog.list()
    if not entries:
        print("(no capabilities registered)")
        return
    for entry in entries:
        print(f"{entry.capability_id} ({entry.spec.get('version', 'unknown')})")


def _cmd_caps_show(args: argparse.Namespace) -> None:
    catalog = CapabilityCatalog(path=_resolve_catalog_path(args.catalog))
    try:
        spec = catalog.get(args.capability_id)
    except CapabilityNotFound as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(spec, indent=2, ensure_ascii=False))


def _cmd_caps_validate(args: argparse.Namespace) -> None:
    path = Path(args.spec)
    try:
        payload = _load_structured(path)
    except Exception as exc:
        print(f"caps validate: failed to load spec: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        validate_capability_spec(payload)
    except ArtifactValidationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print("capability spec is valid")


__all__ = ["register_caps_commands"]
