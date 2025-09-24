from __future__ import annotations

from enum import Enum


class Operation(Enum):
    """Supported step operations inside the generic flow runtime."""

    TASK = "task"
    SWITCH = "switch"
    PARALLEL = "parallel"
    FINISH = "finish"


class ResponseMode(Enum):
    """How the runtime should return results to the caller."""

    IMMEDIATE = "immediate"
    DEFERRED = "deferred"
