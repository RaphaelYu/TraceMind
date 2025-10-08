"""Data model specifications used by service bindings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, Sequence, Set, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from .entity import Entity


_MISSING = object()


Validator = Callable[[Any], bool]


@dataclass(frozen=True)
class FieldSpec:
    """Describe an individual field on a model."""

    name: str
    type: str = "string"
    required: bool = False
    description: Optional[str] = None
    default: Any = field(default_factory=lambda: _MISSING)
    validator: Optional[Validator] = None

    def has_default(self) -> bool:
        return self.default is not _MISSING

    def coerce(self, value: Any) -> Any:
        if value is None:
            if self.required and not self.has_default():
                raise ValueError(f"Field '{self.name}' is required")
            return value
        if self.validator and not self.validator(value):
            raise ValueError(f"Field '{self.name}' rejected value {value!r}")
        return value


@dataclass(frozen=True)
class ModelSpec:
    """Declarative description of a model and its fields."""

    name: str
    fields: Sequence[FieldSpec] = field(default_factory=tuple)
    allow_extra: bool = False

    def __post_init__(self) -> None:
        field_map: Dict[str, FieldSpec] = {}
        for f in self.fields:
            if f.name in field_map:
                raise ValueError(f"Duplicate field '{f.name}' in model '{self.name}'")
            field_map[f.name] = f
        object.__setattr__(self, "_field_map", field_map)

    @property
    def field_names(self) -> Set[str]:
        return set(self._field_map.keys())  # type: ignore[attr-defined]

    def field(self, name: str) -> FieldSpec:
        try:
            return self._field_map[name]  # type: ignore[attr-defined]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise KeyError(f"Unknown field '{name}' for model '{self.name}'") from exc

    def ensure(self, data: Mapping[str, Any], *, partial: bool = False) -> Dict[str, Any]:
        validated: Dict[str, Any] = {}
        provided = set(data.keys())
        for field_spec in self.fields:
            if field_spec.name in data:
                value = field_spec.coerce(data[field_spec.name])
                if value is not _MISSING:
                    validated[field_spec.name] = value
                provided.discard(field_spec.name)
            else:
                if not partial and field_spec.required:
                    raise ValueError(f"Missing field '{field_spec.name}' for model '{self.name}'")
                if field_spec.has_default() and not partial:
                    validated[field_spec.name] = field_spec.default

        if provided and not self.allow_extra:
            extras = ", ".join(sorted(provided))
            raise ValueError(f"Unexpected fields for model '{self.name}': {extras}")

        if self.allow_extra:
            for name in provided:
                validated[name] = data[name]

        return validated

    def make_entity(
        self,
        entity_id: str,
        data: Mapping[str, Any],
        *,
        meta: Optional[MutableMapping[str, Any]] = None,
        partial: bool = False,
    ) -> "Entity":
        from .entity import Entity  # local import to avoid circular dependency

        validated = self.ensure(data, partial=partial)
        return Entity(self, entity_id, dict(validated), dict(meta) if meta is not None else None, partial=partial)
