from __future__ import annotations

from typing import Any, Dict, Optional

from tm.ai.observer import Observation
from tm.ai.proposals import Proposal


def build_mcp_request(
    *,
    tool: str,
    method: str,
    observation: Observation,
    proposal: Optional[Proposal] = None,
    policy: Optional[Dict[str, Any]] = None,
    request_id: int | str = 1,
) -> Dict[str, Any]:
    """Build a JSON-RPC payload for invoking an MCP tool."""

    params: Dict[str, Any] = {
        "observation": {
            "counters": dict(observation.counters),
            "gauges": dict(observation.gauges),
        }
    }

    if policy is not None:
        params["policy"] = policy

    if proposal is not None:
        params["proposal"] = proposal.to_dict()

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": f"{tool}.{method}",
        "params": params,
    }


__all__ = ["build_mcp_request"]
