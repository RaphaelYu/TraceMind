from __future__ import annotations
from ..registry import checks


@checks.check("chk.require_payload")
def chk_require_payload(ctx, call_in):
    if not call_in.get("inputs", {}).get("payload"):
        raise ValueError("missing payload")


@checks.check("chk.emit_metric")
def chk_emit_metric(ctx, call_in):
    # attach logger/metrics here if needed
    return
