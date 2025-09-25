from __future__ import annotations

from typing import Any, Dict, Optional

from tm.ai.observer import Observation
from tm.ai.proposals import Change, Proposal


def propose(observation: Observation, current_policy: Dict[str, Any]) -> Optional[Proposal]:
    """Generate a basic Proposal based on metric thresholds."""

    pending = observation.counter("flows_deferred_pending()", 0.0)
    total_errors = observation.counter("pipeline_steps_total(('status', 'error'),)", 0.0)

    changes = []
    summary_lines = []

    if pending > 5:
        changes.append(Change(path="flow.delay", value=min(current_policy.get("flow", {}).get("delay", 10) + 1, 30)))
        summary_lines.append(f"Increase flow delay due to {pending} pending deferred flows")

    if total_errors > 0:
        changes.append(Change(path="pipeline.auto_pause", value=True))
        summary_lines.append(f"Enable pipeline auto_pause after {total_errors} errors")

    if not changes:
        return None

    summary = "; ".join(summary_lines)
    proposal = Proposal(
        proposal_id="auto-tune",
        title="Automated policy adjustment",
        summary=summary,
        changes=changes,
    )
    return proposal

