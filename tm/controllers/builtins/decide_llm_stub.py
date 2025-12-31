from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from tm.agents.runtime import RuntimeAgent


class DecideLLMStubAgent(RuntimeAgent):
    AGENT_ID = "tm-agent/controller-decide:0.1"
    _DEFAULT_DECISIONS = [
        {
            "effect_ref": "resource:inventory:update",
            "target_state": {"count": 1},
            "reasoning_trace": "builtin.decide.plan",
        }
    ]
    _DETERMINISM_HINTS = {"deterministic", "replayable", "heuristic"}

    def run(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        snapshot = self._resolve_snapshot(inputs)
        intent_id = str(self.config.get("intent_id", "intent.controller.mock"))
        snapshot_id = str(snapshot.get("snapshot_id", "env-mock"))
        plan_id = self.config.get("plan_id") or f"{intent_id}:{snapshot_id}"
        summary = str(self.config.get("summary", "Mock decide plan"))
        decisions = self._build_decisions(plan_id)
        llm_metadata = self._build_llm_metadata()
        policy_requirements = self._resolve_policy_requirements(decisions)
        plan = {
            "plan_id": plan_id,
            "intent_id": intent_id,
            "decisions": decisions,
            "llm_metadata": llm_metadata,
            "summary": summary,
            "policy_requirements": policy_requirements,
            "snapshot_id": snapshot_id,
        }
        self.add_evidence("builtin.decide.plan", {"plan_id": plan_id, "intent_id": intent_id})
        return {"artifact:proposed.plan": plan}

    def _resolve_snapshot(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        payload = inputs.get("state:env.snapshot")
        if not isinstance(payload, Mapping):
            raise RuntimeError("decide agent requires 'state:env.snapshot' input")
        return payload

    def _build_decisions(self, plan_id: str) -> list[Mapping[str, object]]:
        raw = self.config.get("decisions")
        if raw is None:
            raw = self._DEFAULT_DECISIONS
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            raise RuntimeError("decisions must be a sequence of mappings")
        decisions: list[Mapping[str, object]] = []
        for entry in raw:
            if not isinstance(entry, Mapping):
                raise RuntimeError("each decision must be a mapping")
            effect_ref = str(entry.get("effect_ref", self._DEFAULT_DECISIONS[0]["effect_ref"]))
            target_state_raw = entry.get("target_state")
            if not isinstance(target_state_raw, Mapping):
                raise RuntimeError("decision.target_state must be a mapping")
            target_state = dict(target_state_raw)
            reasoning_trace = entry.get("reasoning_trace")
            idempotency_key = str(entry.get("idempotency_key", f"{plan_id}:{effect_ref}"))
            decision: dict[str, object | None] = {
                "effect_ref": effect_ref,
                "target_state": target_state,
                "idempotency_key": idempotency_key,
            }
            if reasoning_trace is not None:
                decision["reasoning_trace"] = str(reasoning_trace)
            decisions.append(decision)
        return decisions

    def _build_llm_metadata(self) -> Mapping[str, object]:
        model = str(self.config.get("model", "tm-llm/controller:0.1"))
        prompt_hash = str(self.config.get("prompt_hash", "mock-prompt"))
        hint = str(self.config.get("determinism_hint", "deterministic"))
        if hint not in self._DETERMINISM_HINTS:
            raise RuntimeError(
                "decide agent determinism_hint must be one of: " + ", ".join(sorted(self._DETERMINISM_HINTS))
            )
        prompt_template_version = str(self.config.get("prompt_template_version", "v0"))
        prompt_version = str(self.config.get("prompt_version", prompt_template_version))
        config_id = self.config.get("llm_config_id")
        metadata = {
            "model": model,
            "prompt_hash": prompt_hash,
            "determinism_hint": hint,
            "prompt_template_version": prompt_template_version,
            "prompt_version": prompt_version,
        }
        if config_id is not None:
            metadata["config_id"] = str(config_id)
        return metadata

    def _resolve_policy_requirements(self, decisions: Iterable[Mapping[str, object]]) -> list[str]:
        raw = self.config.get("policy_requirements")
        if raw is not None:
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
                raise RuntimeError("policy_requirements must be a sequence")
            return [str(item) for item in raw]
        return [str(decision.get("effect_ref", "")) for decision in decisions if decision.get("effect_ref")]
