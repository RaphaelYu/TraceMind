"""Soft bridge to TraceMind's recorder.

We avoid hard dependency on tm.recorder. If it's present and exports
`record_llm_usage`, we'll call it. Otherwise we no-op.
"""

from __future__ import annotations
from typing import Optional

try:
    from tm.recorder import record_llm_usage as _real_record_llm_usage  # type: ignore
except Exception:  # pragma: no cover
    _real_record_llm_usage = None  # type: ignore


def record_llm_usage(
    *,
    provider: str,
    model: str,
    usage,
    flow_id: Optional[str] = None,
    step_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    if _real_record_llm_usage is None:
        return
    try:
        _real_record_llm_usage(provider=provider, model=model, usage=usage, flow_id=flow_id, step_id=step_id, meta=meta)
    except Exception:
        # Recorder must never break the call path
        pass
