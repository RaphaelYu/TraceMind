from __future__ import annotations

import random

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback
    import tomli as tomllib  # type: ignore


@dataclass(frozen=True)
class RetrySettings:
    max_attempts: int = 3
    base_ms: float = 200.0
    factor: float = 2.0
    jitter_ms: float = 50.0
    dlq_after: Optional[int] = None

    def next_delay(self, attempt: int) -> float:
        if attempt <= 0:
            return self.base_ms / 1000.0
        delay_ms = self.base_ms * (self.factor ** (attempt - 1))
        if self.jitter_ms > 0:
            delay_ms += random.uniform(0, self.jitter_ms)
        return max(delay_ms / 1000.0, 0.0)


@dataclass(frozen=True)
class RetryDecision:
    action: str
    delay_seconds: float = 0.0
    reason: Optional[str] = None


class RetryPolicy:
    def __init__(self, default: RetrySettings, per_flow: Mapping[str, RetrySettings] | None = None) -> None:
        self._default = default
        self._per_flow = dict(per_flow or {})

    def settings_for(self, flow_id: str) -> RetrySettings:
        return self._per_flow.get(flow_id, self._default)

    def decide(self, flow_id: str, attempt: int, error: Mapping[str, Any] | None) -> RetryDecision:
        if error is not None:
            retryable = error.get("retryable")
            if retryable is False:
                return RetryDecision(action="dlq", reason="non_retryable")
            code = error.get("error_code")
            if isinstance(code, str) and code in {"POLICY_FORBIDDEN", "VALIDATION_FAILED"}:
                return RetryDecision(action="dlq", reason=code)
        settings = self.settings_for(flow_id)
        max_attempts = max(1, settings.max_attempts)
        if attempt >= max_attempts:
            return RetryDecision(action="dlq", reason="max_attempts")
        dlq_after = settings.dlq_after
        if isinstance(dlq_after, int) and dlq_after >= 0 and attempt >= dlq_after:
            return RetryDecision(action="dlq", reason="dlq_after")
        delay = settings.next_delay(attempt)
        return RetryDecision(action="retry", delay_seconds=delay)


def load_retry_policy(path: str | Path | None = None) -> RetryPolicy:
    config_path = Path(path) if path is not None else Path("trace_config.toml")
    if not config_path.exists():
        return RetryPolicy(RetrySettings())
    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return RetryPolicy(RetrySettings())
    retry_data = _lookup(data, "retries")
    default_settings = _parse_retry_settings(retry_data.get("default"))
    per_flow: Dict[str, RetrySettings] = {}
    flows_raw = retry_data.get("flow")
    if isinstance(flows_raw, Mapping):
        for flow_id, spec in flows_raw.items():
            per_flow[str(flow_id)] = _parse_retry_settings(spec, fallback=default_settings)
    return RetryPolicy(default_settings, per_flow)


def _lookup(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        return {}
    value = data.get(key)
    return value if isinstance(value, Mapping) else {}


def _parse_retry_settings(raw: Any, fallback: RetrySettings | None = None) -> RetrySettings:
    if not isinstance(raw, Mapping):
        return fallback or RetrySettings()
    max_attempts = int(raw.get("max_attempts", fallback.max_attempts if fallback else 3))
    base_ms = float(raw.get("base_ms", fallback.base_ms if fallback else 200.0))
    factor = float(raw.get("factor", fallback.factor if fallback else 2.0))
    jitter_ms = float(raw.get("jitter_ms", fallback.jitter_ms if fallback else 50.0))
    dlq_after_raw = raw.get("dlq_after", fallback.dlq_after if fallback else None)
    if dlq_after_raw is None:
        dlq_after = None
    else:
        dlq_after = int(dlq_after_raw)
    return RetrySettings(
        max_attempts=max(1, max_attempts),
        base_ms=max(0.0, base_ms),
        factor=max(1.0, factor),
        jitter_ms=max(0.0, jitter_ms),
        dlq_after=dlq_after,
    )


__all__ = [
    "RetrySettings",
    "RetryDecision",
    "RetryPolicy",
    "load_retry_policy",
]
