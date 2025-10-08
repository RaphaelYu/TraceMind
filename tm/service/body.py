"""High-level service wrapper that validates input and triggers flows."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:  # pragma: no cover - optional dependency shim
    from tm.flow.operations import ResponseMode
except ModuleNotFoundError:  # pragma: no cover
    from enum import Enum

    class ResponseMode(Enum):  # type: ignore[redefinition]
        IMMEDIATE = "immediate"
        DEFERRED = "deferred"


from tm.model.entity import Entity
from tm.model.spec import ModelSpec

from .binding import BindingSpec, Operation
from .router import OperationRouter, RuntimeLike


@dataclass
class ServiceBody:
    model: ModelSpec
    runtime: RuntimeLike
    binding: BindingSpec
    router: OperationRouter | None = None

    def __post_init__(self) -> None:
        if self.router is None:
            self.router = OperationRouter(self.runtime, {self.model.name: self.binding})

    def _ensure_entity(
        self,
        operation: Operation,
        payload: MutableMapping[str, Any],
        *,
        entity_id: Optional[str] = None,
        partial: bool = False,
    ) -> Entity:
        payload_dict = dict(payload)
        body = payload_dict.get("data")
        if not isinstance(body, MutableMapping):
            body = {k: v for k, v in payload_dict.items() if k not in {"id", "meta", "data"}}

        meta = payload_dict.get("meta") if isinstance(payload_dict.get("meta"), MutableMapping) else None

        guess_id = entity_id or payload_dict.get("id")
        if isinstance(body, MutableMapping) and not guess_id:
            guess_id = body.get("id")
        if not isinstance(guess_id, str) or not guess_id:
            guess_id = "_"

        return self.model.make_entity(guess_id, body, meta=meta, partial=partial)

    async def handle(
        self,
        operation: Operation | str,
        payload: MutableMapping[str, Any],
        *,
        entity_id: Optional[str] = None,
        response_mode: Optional[ResponseMode] = None,
        context: Optional[Dict[str, Any]] = None,
        partial: bool = False,
    ) -> Dict[str, object]:
        op_enum = operation if isinstance(operation, Operation) else Operation(operation)
        entity = self._ensure_entity(op_enum, payload, entity_id=entity_id, partial=partial)

        dispatch_payload: Dict[str, object] = {
            "entity": entity.to_dict(),
            "data": entity.attributes,
        }
        if entity.meta is not None:
            dispatch_payload["meta"] = entity.meta

        result = await self.router.dispatch(  # type: ignore[union-attr]
            model=self.model.name,
            operation=op_enum,
            payload=dispatch_payload,
            context={"entity": entity, **(context or {})},
            response_mode=response_mode,
        )

        return {"entity": entity.to_dict(), **result}
