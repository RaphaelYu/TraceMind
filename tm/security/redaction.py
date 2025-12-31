"""Helpers that mask registered secrets inside strings, mappings, and sequences."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence as AbcSequence
from typing import Any, Iterable, List, Tuple


class Redactor:
    """Masks registered secrets by substitution with a fixed placeholder."""

    def __init__(self, secrets: Iterable[str], mask: str = "[REDACTED]", case_sensitive: bool = False):
        sanitized: List[str] = []
        for secret in secrets:
            value = secret.strip()
            if value and value not in sanitized:
                sanitized.append(value)
        sanitized.sort(key=len, reverse=True)
        flags = 0 if case_sensitive else re.IGNORECASE
        self._patterns: List[Tuple[str, re.Pattern[str]]] = [
            (secret, re.compile(re.escape(secret), flags)) for secret in sanitized
        ]
        self.mask = mask

    def redact_string(self, value: str) -> str:
        if not self._patterns:
            return value
        output = value
        for _, pattern in self._patterns:
            output = pattern.sub(self.mask, output)
        return output

    def redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_string(value)
        if isinstance(value, Mapping):
            return {key: self.redact(val) for key, val in value.items()}
        if isinstance(value, AbcSequence) and not isinstance(value, (str, bytes, bytearray)):
            masked = [self.redact(item) for item in value]
            if isinstance(value, list):
                return masked
            if isinstance(value, tuple):
                return tuple(masked)
            if isinstance(value, set):
                return set(masked)
            return masked
        return value
