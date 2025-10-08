from __future__ import annotations
import dataclasses
from typing import Protocol, runtime_checkable, Optional, Literal

ErrorCode = Literal[
    "RUN_TIMEOUT",
    "RUN_CANCELLED",
    "QUEUE_TIMEOUT",
    "PROVIDER_ERROR",
    "BAD_REQUEST",
    "RATE_LIMIT",
]


@dataclasses.dataclass
class LlmUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Optional[float] = None


@dataclasses.dataclass
class LlmCallResult:
    output_text: str
    usage: LlmUsage
    raw: Optional[dict] = None


class LlmError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message


@runtime_checkable
class Provider(Protocol):
    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout_s: Optional[float] = None,
    ) -> LlmCallResult: ...
