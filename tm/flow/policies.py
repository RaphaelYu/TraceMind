from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from .operations import ResponseMode


@dataclass
class RetryPolicy:
    """Simple retry settings for a step."""

    max_attempts: int = 1  # 1 = no retry
    backoff_ms: int = 0  # fixed backoff between attempts


@dataclass
class TimeoutPolicy:
    """Simple timeout settings for a step."""

    timeout_ms: Optional[int] = None  # None = no timeout


@dataclass
class StepPolicies:
    """Bundle of policies applied to a step."""

    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout: TimeoutPolicy = field(default_factory=TimeoutPolicy)


@dataclass
class FlowPolicies:
    """Top-level runtime policies that influence flow execution."""

    response_mode: ResponseMode = ResponseMode.IMMEDIATE
    max_concurrency: Optional[int] = None
    allow_deferred: bool = True
    short_wait_s: float = 0.0


def parse_policies_from_cfg(cfg: Dict[str, Any]) -> StepPolicies:
    """
    Parse retry/timeout from a step's cfg.
    Supports either:
      - retry={"max_attempts": N, "backoff_ms": M}
      - timeout_ms=...  OR  timeout={"timeout_ms": ...}
    """
    r_raw = cfg.get("retry", {})
    r = r_raw if isinstance(r_raw, dict) else {}
    t = cfg.get("timeout_ms", None)
    timeout_cfg = cfg.get("timeout")
    if isinstance(timeout_cfg, dict):
        t = timeout_cfg.get("timeout_ms", t)
    return StepPolicies(
        retry=RetryPolicy(
            max_attempts=_as_int(r.get("max_attempts"), default=1),
            backoff_ms=_as_int(r.get("backoff_ms"), default=0),
        ),
        timeout=TimeoutPolicy(
            timeout_ms=None if t in (None, "", 0) else _as_int(t, default=0),
        ),
    )


def _as_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default
