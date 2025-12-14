from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .adapter import TraceMindAdapter
from .ctl import Expr, eval_state_expr, has_ctl_nodes, parse_expr
from .explorer import ExplorationResult


@dataclass
class InvariantResult:
    expr: str
    ok: bool
    violated_at: Optional[int]
    path: List[int]
    reason: str


def check_invariants(
    invariants: List[str], model: ExplorationResult, adapter: TraceMindAdapter
) -> List[InvariantResult]:
    results: List[InvariantResult] = []
    for raw in invariants:
        try:
            expr: Expr = parse_expr(raw)
        except Exception as exc:
            results.append(InvariantResult(expr=raw, ok=False, violated_at=None, path=[], reason=f"parse error: {exc}"))
            continue
        if has_ctl_nodes(expr):
            results.append(
                InvariantResult(
                    expr=raw,
                    ok=False,
                    violated_at=None,
                    path=[],
                    reason="CTL operators are not allowed in invariants",
                )
            )
            continue
        violated_at: Optional[int] = None
        for idx, state in enumerate(model.states):
            if not eval_state_expr(expr, state, adapter):
                violated_at = idx
                break
        if violated_at is None:
            results.append(InvariantResult(expr=raw, ok=True, violated_at=None, path=[], reason=""))
        else:
            path = model.path_to(violated_at)
            results.append(InvariantResult(expr=raw, ok=False, violated_at=violated_at, path=path, reason="violated"))
    return results
