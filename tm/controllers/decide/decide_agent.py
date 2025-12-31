from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tm.ai.llm_client import make_client
from tm.ai.providers.base import LlmCallResult, LlmError
from tm.ai.recorder_bridge import record_llm_usage
from tm.agents.runtime import RuntimeAgent
from tm.artifacts.normalize import normalize_body
from tm.controllers.models import LlmMetadata
from tm.controllers.decide.llm_record import LlmRecordStore
from tm.utils.templating import render_template


class DecideAgent(RuntimeAgent):
    AGENT_ID = "tm-agent/controller-decide:0.2"
    _DEFAULT_DECISIONS: list[Mapping[str, Any]] = [
        {
            "effect_ref": "resource:inventory:update",
            "target_state": {"count": 1},
        }
    ]

    def run(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        snapshot = self._resolve_snapshot(inputs)
        inputs_hash = self._inputs_hash(snapshot)
        mode = str(self.config.get("mode", "live")).strip().lower()
        store = LlmRecordStore(self.config.get("record_path"))
        if mode == "replay":
            plan = store.get(inputs_hash)
            if plan is None:
                raise RuntimeError(f"no recorded plan for inputs hash '{inputs_hash}'")
            self.add_evidence("builtin.decide.plan", {"plan_id": plan.get("plan_id"), "mode": "replay"})
            return {"artifact:proposed.plan": plan}
        intent_id = str(self.config.get("intent_id", "intent.controller.decide"))
        plan_id = str(self.config.get("plan_id") or f"{intent_id}:{inputs_hash}")
        summary = str(self.config.get("summary", f"Decision plan for {intent_id}"))
        template_version, template_body = self._load_prompt_template()
        prompt = self._render_prompt(
            template_body, snapshot, summary, intent_id, inputs_hash, self._render_decisions_preview()
        )
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        llm_result = self._invoke_llm(
            provider=self.config.get("provider"),
            model=self.config.get("model"),
            prompt=prompt,
        )
        summary = summary or llm_result.output_text
        decisions = self._resolve_decisions(plan_id)
        policy_requirements = self._resolve_policy_requirements(decisions)
        model_id = str(self.config.get("model_id", "tm-llm/controller"))
        model_version = str(self.config.get("model_version", "0.1"))
        determinism = str(self.config.get("determinism_hint", "replayable"))
        if determinism not in LlmMetadata.OPTIONS:
            raise RuntimeError("determinism_hint must be one of: " + ", ".join(sorted(LlmMetadata.OPTIONS)))
        prompt_version = str(self.config.get("prompt_version") or template_version)
        config_id = self.config.get("llm_config_id")
        llm_metadata: dict[str, Any] = {
            "model": str(self.config.get("model", "tm-llm/mock")),
            "prompt_hash": prompt_hash,
            "determinism_hint": determinism,
            "model_id": model_id,
            "model_version": model_version,
            "prompt_template_version": template_version,
            "prompt_version": prompt_version,
            "config_id": str(config_id) if config_id is not None else None,
            "inputs_hash": inputs_hash,
        }
        plan = {
            "plan_id": plan_id,
            "intent_id": intent_id,
            "decisions": decisions,
            "llm_metadata": llm_metadata,
            "summary": summary,
            "policy_requirements": policy_requirements,
        }
        store.set(
            inputs_hash,
            plan,
            {
                "provider": str(self.config.get("provider", "fake")),
                "model": str(self.config.get("model", "tm-llm/mock")),
                "prompt_hash": prompt_hash,
            },
        )
        self.add_evidence("builtin.decide.plan", {"plan_id": plan_id, "mode": "live"})
        return {"artifact:proposed.plan": plan}

    def _resolve_snapshot(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        payload = inputs.get("state:env.snapshot")
        if not isinstance(payload, Mapping):
            raise RuntimeError("decide agent requires 'state:env.snapshot' input")
        return dict(payload)

    def _inputs_hash(self, snapshot: Mapping[str, object]) -> str:
        normalized = normalize_body({"snapshot": snapshot})
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _load_prompt_template(self) -> tuple[str, str]:
        base = Path(__file__).resolve().parent
        requested_version = str(self.config.get("prompt_template_version") or "").strip()
        template_name = f"{requested_version or 'v0'}.md"
        template_path = base / "prompt_templates" / template_name
        if not template_path.exists():
            template_path = base / "prompt_templates" / "v0.md"
        content = template_path.read_text(encoding="utf-8").splitlines()
        version = template_path.stem
        body_lines: list[str] = []
        for line in content:
            stripped = line.strip()
            if stripped.startswith("prompt_template_version:"):
                version = stripped.split(":", 1)[1].strip()
                continue
            body_lines.append(line)
        body = "\n".join(body_lines).lstrip()
        return version, body

    def _render_prompt(
        self,
        template: str,
        snapshot: Mapping[str, object],
        summary: str,
        intent_id: str,
        inputs_hash: str,
        decisions_preview: str,
    ) -> str:
        payload = {
            "snapshot": json.dumps(snapshot, sort_keys=True),
            "summary": summary,
            "intent_id": intent_id,
            "inputs_hash": inputs_hash,
            "decisions": decisions_preview,
        }
        return render_template(template, payload)

    def _render_decisions_preview(self) -> str:
        return json.dumps(self._DEFAULT_DECISIONS, sort_keys=True)

    def _invoke_llm(self, provider: Any, model: Any, prompt: str) -> "LlmCallResult":
        provider_name = str(provider or "fake")
        model_name = str(model or "tm-llm/mock")
        client = make_client(provider_name)

        async def _call() -> "LlmCallResult":
            return await client.call(model=model_name, prompt=prompt)

        try:
            result = asyncio.run(_call())
        except LlmError as exc:
            raise RuntimeError(f"LLM error: {exc.code}") from exc
        except Exception as exc:
            raise RuntimeError("failed to call LLM") from exc
        try:
            record_llm_usage(provider=provider_name, model=model_name, usage=result.usage)
        except Exception:
            pass
        return result

    def _resolve_decisions(self, plan_id: str) -> list[Mapping[str, Any]]:
        has = self.config.get("decisions")
        if has is None:
            candidates = self._DEFAULT_DECISIONS
        else:
            if not isinstance(has, Sequence) or isinstance(has, (str, bytes, bytearray)):
                raise RuntimeError("decisions must be a sequence")
            candidates = [dict(entry) for entry in has if isinstance(entry, Mapping)]
        decisions: list[Mapping[str, Any]] = []
        for entry in candidates:
            effect_ref = str(entry.get("effect_ref", self._DEFAULT_DECISIONS[0]["effect_ref"]))
            target_state = entry.get("target_state")
            if not isinstance(target_state, Mapping):
                raise RuntimeError("decision.target_state must be a mapping")
            idempotency_key = str(entry.get("idempotency_key", f"{plan_id}:{effect_ref}"))
            decision: dict[str, Any] = {
                "effect_ref": effect_ref,
                "target_state": dict(target_state),
                "idempotency_key": idempotency_key,
            }
            reasoning_trace = entry.get("reasoning_trace")
            if reasoning_trace is not None:
                decision["reasoning_trace"] = str(reasoning_trace)
            decisions.append(decision)
        return decisions

    def _resolve_policy_requirements(self, decisions: Iterable[Mapping[str, Any]]) -> list[str]:
        raw = self.config.get("policy_requirements")
        if raw is not None:
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
                raise RuntimeError("policy_requirements must be a sequence")
            return [str(item) for item in raw]
        return [str(decision.get("effect_ref", "")) for decision in decisions if decision.get("effect_ref")]
