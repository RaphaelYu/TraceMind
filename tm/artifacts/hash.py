from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .normalize import normalize_body


def body_hash(body: Any, schema_hints: Mapping[str, Any] | None = None) -> str:
    canonical = normalize_body(body, schema_hints)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["body_hash"]
