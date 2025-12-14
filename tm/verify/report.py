from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from .adapter import TraceMindAdapter
from .ctl import Expr, Not, check_ctl, parse_expr
from .explorer import ExplorationResult
from .invariants import InvariantResult, check_invariants
from .spec import PropertySpec


@dataclass
class PropertyResult:
    name: str
    formula: str
    ok: bool
    counterexample: List[int]
    reason: str


@dataclass
class VerifyReport:
    invariants: List[InvariantResult]
    properties: List[PropertyResult]
    explored_states: int
    deadlocks: List[int]
    hash_mode: str
    max_depth: int

    def as_dict(self) -> dict:
        return {
            "explored_states": self.explored_states,
            "deadlocks": self.deadlocks,
            "hash_mode": self.hash_mode,
            "max_depth": self.max_depth,
            "invariants": [
                {
                    "expr": inv.expr,
                    "ok": inv.ok,
                    "violated_at": inv.violated_at,
                    "path": inv.path,
                    "reason": inv.reason,
                }
                for inv in self.invariants
            ],
            "properties": [
                {
                    "name": prop.name,
                    "formula": prop.formula,
                    "ok": prop.ok,
                    "counterexample": prop.counterexample,
                    "reason": prop.reason,
                }
                for prop in self.properties
            ],
        }


def _nearest_reachable(targets: Sequence[int], model: ExplorationResult) -> Optional[int]:
    available = set(targets)
    if not available:
        return None
    for idx in range(len(model.states)):
        if idx in available:
            return idx
    return None


def _counterexample(expr: Expr, model: ExplorationResult, adapter: TraceMindAdapter) -> List[int]:
    neg = Not(expr)
    sat_neg = check_ctl(neg, model, adapter)
    target = _nearest_reachable(sorted(sat_neg), model)
    if target is None:
        return []
    return model.path_to(target)


def check_properties(
    props: Sequence[PropertySpec], model: ExplorationResult, adapter: TraceMindAdapter
) -> List[PropertyResult]:
    results: List[PropertyResult] = []
    for spec in props:
        try:
            expr = parse_expr(spec.formula)
            sat = check_ctl(expr, model, adapter)
            ok = 0 in sat
            path: List[int] = []
            reason = ""
            if not ok:
                path = _counterexample(expr, model, adapter)
                reason = "not satisfied from initial state"
            results.append(
                PropertyResult(name=spec.name, formula=spec.formula, ok=ok, counterexample=path, reason=reason)
            )
        except Exception as exc:
            results.append(
                PropertyResult(
                    name=spec.name, formula=spec.formula, ok=False, counterexample=[], reason=f"parse error: {exc}"
                )
            )
    return results


def build_report(
    *,
    invariants: Sequence[str],
    properties: Sequence[PropertySpec],
    model: ExplorationResult,
    adapter: TraceMindAdapter,
) -> VerifyReport:
    inv_results = check_invariants(list(invariants), model, adapter)
    prop_results = check_properties(properties, model, adapter)
    return VerifyReport(
        invariants=inv_results,
        properties=prop_results,
        explored_states=len(model.states),
        deadlocks=model.deadlocks,
        hash_mode=model.hash_mode,
        max_depth=model.max_depth,
    )
