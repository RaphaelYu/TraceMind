from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from tm.artifacts import validate_policy_spec


@dataclass(frozen=True)
class IterationResult:
    policy: Mapping[str, Any]
    applied_patch: Mapping[str, Any]
    approval: str


def apply_patch_proposal(policy: Mapping[str, Any], proposal: Mapping[str, Any]) -> Mapping[str, Any]:
    updated: MutableMapping[str, Any] = copy.deepcopy(dict(policy))
    for change in proposal.get("changes", []):
        path = str(change["path"])
        parts = [segment for segment in path.split(".") if segment]
        target: MutableMapping[str, Any] = updated
        for segment in parts[:-1]:
            target = target.setdefault(segment, {})
        leaf = parts[-1]
        if change.get("op") == "remove":
            target.pop(leaf, None)
        else:
            target[leaf] = change.get("value")
    version = str(updated.get("version", "0")).split(".")
    try:
        major, minor, patch = (int(part) for part in version[:3])
    except Exception:
        major, minor, patch = 1, 0, 0
    patch += 1
    updated["version"] = f"{major}.{minor}.{patch}"
    validate_policy_spec(updated)
    return updated


def run_iteration(
    draft_policy: Mapping[str, Any],
    *,
    patch_proposal: Mapping[str, Any],
    approval: str = "manual",
) -> IterationResult:
    if patch_proposal.get("source") != "violation":
        raise RuntimeError("Iteration only supports violation-driven patches")
    approved_policy = apply_patch_proposal(draft_policy, patch_proposal)
    return IterationResult(policy=approved_policy, applied_patch=patch_proposal, approval=approval)
