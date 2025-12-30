from __future__ import annotations

from typing import Dict, Mapping, Sequence

from tm.agents.registry import AgentRegistry, default_registry

from tm.artifacts import Artifact, ArtifactStatus, ArtifactType
from tm.artifacts.models import AgentBundleBody, AgentBundlePlanStep
from tm.policy.guard import PolicyGuard
from tm.runtime.context import ExecutionContext


class AgentBundleExecutorError(RuntimeError):
    """Raised when execution cannot proceed."""


class AgentBundleExecutor:
    def __init__(self, registry: AgentRegistry | None = None, guard: PolicyGuard | None = None) -> None:
        self._registry = registry or default_registry()
        self._policy_guard = guard or PolicyGuard()

    def execute(
        self,
        artifact: Artifact,
        configs: Mapping[str, Mapping[str, object]] | None = None,
        context: ExecutionContext | None = None,
    ) -> ExecutionContext:
        if artifact.envelope.status != ArtifactStatus.ACCEPTED:
            raise AgentBundleExecutorError("artifact must be accepted")
        if artifact.envelope.artifact_type != ArtifactType.AGENT_BUNDLE:
            raise AgentBundleExecutorError("expected agent_bundle artifact")
        body = artifact.body
        if not isinstance(body, AgentBundleBody):
            raise AgentBundleExecutorError("invalid agent_bundle body")
        context = context or ExecutionContext()
        configs = configs or {}
        self._load_preconditions(body, context)
        agents = {agent.spec.agent_id: agent for agent in body.agents}
        for step in body.plan:
            agent_entry = agents.get(step.agent_id)
            if agent_entry is None:
                raise AgentBundleExecutorError(f"step '{step.step}' references unknown agent '{step.agent_id}'")
            runtime_agent = self._registry.resolve(
                agent_entry.spec.agent_id,
                agent_entry.spec,
                configs.get(agent_entry.spec.agent_id, {}),
            )
            inputs = self._collect_inputs(step, context)
            resource_effects = [effect for effect in agent_entry.spec.contract.effects if effect.kind == "resource"]
            for effect in resource_effects:
                decision = self._policy_guard.evaluate(effect, context, body.meta)
                if not decision.allowed:
                    raise AgentBundleExecutorError(
                        f"policy guard denied effect '{effect.name}' on '{effect.target}': {decision.reason}"
                    )
            runtime_agent.init({"step": step.step})
            outputs = context.run_idempotent(
                f"{agent_entry.spec.agent_id}:{step.step}",
                lambda: runtime_agent.run(inputs),
            )
            agent_evidence = runtime_agent.state.metadata.get("agent_evidence", [])
            runtime_agent.finalize()
            self._persist_outputs(step, context, outputs)
            metadata = context.metadata
            metadata.setdefault("executed_steps", []).append(step.step)
            step_outputs = metadata.setdefault("step_outputs", {})
            step_outputs[step.step] = {ref: outputs[ref] for ref in step.outputs}
            for entry in agent_evidence:
                context.evidence.record(entry["kind"], entry["payload"])
            agent_evidence = runtime_agent.state.metadata.pop("agent_evidence", [])
            for entry in agent_evidence:
                context.evidence.record(entry["kind"], entry["payload"])
        return context

    def _collect_inputs(self, step: AgentBundlePlanStep, context: ExecutionContext) -> Dict[str, object]:
        result: Dict[str, object] = {}
        for ref in step.inputs:
            try:
                result[ref] = context.get_ref(ref)
            except KeyError as exc:
                raise AgentBundleExecutorError(f"missing input ref '{ref}' in step '{step.step}'") from exc
        return result

    def _persist_outputs(
        self, step: AgentBundlePlanStep, context: ExecutionContext, outputs: Mapping[str, object]
    ) -> None:
        for ref in step.outputs:
            if ref not in outputs:
                raise AgentBundleExecutorError(f"agent '{step.agent_id}' did not produce output '{ref}'")
            context.set_ref(ref, outputs[ref])

    def _load_preconditions(self, bundle: AgentBundleBody, context: ExecutionContext) -> None:
        meta = bundle.meta if isinstance(bundle.meta, Mapping) else {}
        raw_preconditions = meta.get("preconditions", [])
        if isinstance(raw_preconditions, Sequence) and not isinstance(raw_preconditions, (str, bytes, bytearray)):
            preconditions = [str(item) for item in raw_preconditions]
        else:
            preconditions = []
        for ref in preconditions:
            try:
                context.get_ref(ref)
            except KeyError:
                context.set_ref(ref, {})
