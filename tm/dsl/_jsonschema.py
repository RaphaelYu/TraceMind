from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence


try:  # pragma: no cover - prefer native jsonschema when available
    from jsonschema import Draft202012Validator, ValidationError  # type: ignore
except ModuleNotFoundError:

    @dataclass
    class ValidationError(Exception):
        message: str
        path: Sequence[Any]

        def __post_init__(self) -> None:
            super().__init__(self.message)
            self.absolute_path = list(self.path)

    class Draft202012Validator:
        def __init__(self, schema: Mapping[str, Any]) -> None:
            self.schema = schema

        def iter_errors(self, instance: Any) -> Iterator[ValidationError]:
            yield from _iter_errors(self.schema, instance, ())


def _iter_errors(schema: Mapping[str, Any], instance: Any, path: Sequence[Any]) -> Iterator[ValidationError]:
    type_decl = schema.get("type")
    if type_decl:
        if not _check_type(type_decl, instance):
            yield ValidationError(f"Expected type {type_decl!r}", path)
            return

    if "const" in schema and instance != schema["const"]:
        yield ValidationError(f"Expected constant value {schema['const']!r}", path)

    if "enum" in schema and instance not in schema["enum"]:
        yield ValidationError(f"Value {instance!r} not in enum {schema['enum']!r}", path)

    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if pattern and not re.match(pattern, instance):
            yield ValidationError(f"String {instance!r} does not match pattern {pattern!r}", path)

    if isinstance(instance, int):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            yield ValidationError(f"{instance} is less than minimum {minimum}", path)
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            yield ValidationError(f"{instance} is greater than maximum {maximum}", path)

    if isinstance(instance, Mapping):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                yield ValidationError(f"Missing required property {key!r}", path + (key,))
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                yield from _iter_errors(properties[key], value, path + (key,))
            elif additional is False:
                yield ValidationError(f"Additional property {key!r} not allowed", path + (key,))
            elif isinstance(additional, Mapping):
                yield from _iter_errors(additional, value, path + (key,))

    if isinstance(instance, Sequence) and not isinstance(instance, (str, bytes, bytearray)):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            yield ValidationError(f"Expected at least {schema['minItems']} items", path)
        items_schema = schema.get("items")
        if isinstance(items_schema, Mapping):
            for idx, value in enumerate(instance):
                yield from _iter_errors(items_schema, value, path + (idx,))


def _check_type(type_decl: Any, instance: Any) -> bool:
    if type_decl == "object":
        return isinstance(instance, Mapping)
    if type_decl == "array":
        return isinstance(instance, Sequence) and not isinstance(instance, (str, bytes, bytearray))
    if type_decl == "string":
        return isinstance(instance, str)
    if type_decl == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_decl == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if type_decl == "boolean":
        return isinstance(instance, bool)
    if type_decl == "null":
        return instance is None
    return True


__all__ = ["Draft202012Validator", "ValidationError"]
