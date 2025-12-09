"""Soft bridge to TraceMind's recorder.

We avoid hard dependency on tm.recorder. If it's present and exports
`record_llm_usage`, we'll call it. Otherwise we no-op.
"""

from __future__ import annotations
from typing import Callable, Optional

try:
    from tm.recorder import record_llm_usage as _real_record_llm_usage
except Exception:  # pragma: no cover
    _real_record_llm_usage = None


def record_llm_usage(
    *,
    provider: str,
    model: str,
    usage,
    flow_id: Optional[str] = None,
    step_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    recorder: Optional[Callable[..., None]] = _real_record_llm_usage
    if recorder is None:
        return
    try:
        recorder(provider=provider, model=model, usage=usage, flow_id=flow_id, step_id=step_id, meta=meta)
    except Exception:
        # Recorder must never break the call path
        pass
