from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from tm.agents.runtime import RuntimeAgent
from tm.artifacts.normalize import normalize_body


class ActMockAgent(RuntimeAgent):
    AGENT_ID = "tm-agent/controller-act:0.1"

    def run(self, inputs: Mapping[str, Any]) -> Mapping[str, object]:
        snapshot = self._resolve_snapshot(inputs)
        plan = self._resolve_plan(inputs)
        decisions_raw = plan.get("decisions")
        if not isinstance(decisions_raw, Sequence) or isinstance(decisions_raw, (str, bytes, bytearray)):
            raise RuntimeError("plan.decisions must be a sequence")
        decisions: list[Mapping[str, object]] = []
        for entry in decisions_raw:
            if not isinstance(entry, Mapping):
                raise RuntimeError("each decision must be a mapping")
            decisions.append(dict(entry))
        artifact_refs = self._apply_decisions(decisions)
        policy_decisions = [
            {
                "effect_ref": str(decision.get("effect_ref", "")),
                "allowed": True,
                "reason": "allowlist",
                "idempotency_key": str(decision.get("idempotency_key", "")),
            }
            for decision in decisions
        ]
        status = "succeeded"
        report = {
            "report_id": plan["plan_id"],
            "artifact_refs": artifact_refs,
            "status": status,
            "policy_decisions": policy_decisions,
            "errors": [],
            "artifacts": {
                "ObserveAgent": {
                    "snapshot_id": snapshot.get("snapshot_id"),
                    "data_hash": snapshot.get("data_hash"),
                },
                "DecideAgent": {
                    "plan_id": plan["plan_id"],
                    "summary": plan.get("summary"),
                },
                "ActAgent": {"artifact_refs": artifact_refs},
            },
        }
        execution_hash = self._hash_execution(report)
        report["execution_hash"] = execution_hash
        self.add_evidence("builtin.act.report", {"report_id": report["report_id"], "execution_hash": execution_hash})
        return {
            "artifact:execution.report": report,
            "state:act.result": {"artifact_refs": artifact_refs, "status": status},
        }

    def _resolve_snapshot(self, inputs: Mapping[str, Any]) -> Mapping[str, object]:
        payload = inputs.get("state:env.snapshot")
        if not isinstance(payload, Mapping):
            raise RuntimeError("act agent requires 'state:env.snapshot' input")
        return payload

    def _resolve_plan(self, inputs: Mapping[str, Any]) -> Mapping[str, object]:
        payload = inputs.get("artifact:proposed.plan")
        if not isinstance(payload, Mapping):
            raise RuntimeError("act agent requires 'artifact:proposed.plan' input")
        return dict(payload)

    def _apply_decisions(self, decisions: Sequence[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
        resources = self.state.metadata.setdefault("mock_resources", {})
        artifact_refs: dict[str, Mapping[str, object]] = {}
        for decision in decisions:
            effect_ref = str(decision.get("effect_ref", ""))
            target_state_raw = decision.get("target_state")
            if not isinstance(target_state_raw, Mapping):
                raise RuntimeError("decision.target_state must be a mapping")
            current = resources.setdefault(effect_ref, {})
            current.update(dict(target_state_raw))
            artifact_refs[effect_ref] = {**current, "status": "applied"}
        return artifact_refs

    def _hash_execution(self, report: Mapping[str, Any]) -> str:
        normalized = normalize_body(
            {
                "artifact_refs": report.get("artifact_refs", {}),
                "policy_decisions": report.get("policy_decisions", []),
                "status": report.get("status", ""),
            }
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
