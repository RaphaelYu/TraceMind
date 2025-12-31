from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from tm.agents.models import EffectIdempotency, EffectRef
from tm.agents.registry import default_registry as default_agent_registry
from tm.agents.runtime import RuntimeAgent
from tm.llm.config_registry import LlmConfigEntry
from tm.artifacts import (
    Artifact,
    ArtifactEnvelope,
    ArtifactRegistry,
    ArtifactStatus,
    ArtifactType,
    EnvSnapshotBody,
    ExecutionReportBody,
    ProposedChangePlanBody,
    verify,
)
from tm.artifacts.models import AgentBundleAgent, AgentBundleBody, AgentBundlePlanStep
from tm.artifacts.registry import default_registry as default_artifact_registry
from tm.policy.guard import PolicyDecision, PolicyGuard
from tm.runtime.context import ExecutionContext
from tm.runtime.executor import AgentBundleExecutorError
from tm.runtime.reliability import (
    ReliabilityProfile,
    RunReliabilityController,
    StepTimeoutError,
    run_with_timeout,
)
from tm.utils.yaml import import_yaml

from . import builtins  # noqa: F401  ensure builtin controller agents register
from .decide.decide_agent import DecideAgent

yaml = import_yaml()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in normalized)
    return "-".join(part for part in cleaned.split("-") if part)


def _write_doc(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=True, allow_unicode=True)
        return
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _collect_inputs(step: AgentBundlePlanStep, context: ExecutionContext) -> Mapping[str, Any]:
    inputs: dict[str, Any] = {}
    for ref in step.inputs:
        try:
            inputs[ref] = context.get_ref(ref)
        except KeyError as exc:
            raise ControllerCycleError(f"missing input '{ref}' for step '{step.step}'", errors=[str(exc)]) from exc
    return inputs


def _persist_outputs(step: AgentBundlePlanStep, context: ExecutionContext, outputs: Mapping[str, Any]) -> None:
    for ref in step.outputs:
        if ref not in outputs:
            raise AgentBundleExecutorError(
                f"agent '{step.agent_id}' did not produce output '{ref}' for step '{step.step}'"
            )
        context.set_ref(ref, outputs[ref])


def _artifact_document(artifact: Artifact) -> dict[str, Any]:
    envelope = asdict(artifact.envelope)
    envelope["status"] = artifact.envelope.status.value
    envelope["artifact_type"] = artifact.envelope.artifact_type.value
    if artifact.envelope.signature is None:
        envelope.pop("signature", None)
    return {"envelope": envelope, "body": dict(artifact.body_raw)}


def _build_gap_map_doc(bundle_id: str, errors: Sequence[str], created_at: str) -> dict[str, Any]:
    description = (
        "Controller cycle detected blocking issues: " + "; ".join(errors)
        if errors
        else "Controller cycle completed without blocking gaps."
    )
    mitigations = list(errors) if errors else ["No additional mitigation required."]
    severity = "high" if errors else "low"
    return {
        "envelope": {
            "artifact_id": f"tm-controller/gap-map-{_slug(bundle_id)}",
            "status": ArtifactStatus.CANDIDATE.value,
            "artifact_type": ArtifactType.GAP_MAP.value,
            "version": "v0",
            "created_by": "controller.cycle",
            "created_at": created_at,
            "body_hash": "",
            "envelope_hash": "",
            "meta": {"phase": "controller-cycle"},
        },
        "body": {
            "gap_id": f"gap-{_slug(bundle_id)}",
            "gap_description": description,
            "impacted_intents": [bundle_id],
            "mitigations": mitigations,
            "severity": severity,
        },
    }


def _build_backlog_doc(bundle_id: str, errors: Sequence[str], created_at: str) -> dict[str, Any]:
    description = "Resolve: " + "; ".join(errors) if errors else f"Review controller cycle for bundle {bundle_id}."
    priority = "high" if errors else "low"
    return {
        "envelope": {
            "artifact_id": f"tm-controller/backlog-{_slug(bundle_id)}",
            "status": ArtifactStatus.CANDIDATE.value,
            "artifact_type": ArtifactType.BACKLOG.value,
            "version": "v0",
            "created_by": "controller.cycle",
            "created_at": created_at,
            "body_hash": "",
            "envelope_hash": "",
            "meta": {"phase": "controller-cycle"},
        },
        "body": {
            "backlog_id": f"backlog-{_slug(bundle_id)}",
            "items": [
                {
                    "intent_id": bundle_id,
                    "priority": priority,
                    "description": description,
                }
            ],
        },
    }


def write_gap_and_backlog(report_path: Path, bundle_id: str, errors: Sequence[str]) -> tuple[Path, Path]:
    created_at = _iso_now()
    gap_path = report_path.parent / "gap_map.yaml"
    backlog_path = report_path.parent / "backlog.yaml"
    _write_doc(gap_path, _build_gap_map_doc(bundle_id, errors, created_at))
    _write_doc(backlog_path, _build_backlog_doc(bundle_id, errors, created_at))
    return gap_path, backlog_path


class ControllerCycleError(RuntimeError):
    def __init__(self, message: str, *, errors: Sequence[str] | None = None):
        super().__init__(message)
        self.errors = list(errors) if errors else [message]


@dataclass
class ControllerCycleResult:
    bundle_artifact_id: str
    env_snapshot: Artifact
    planned_change: Artifact
    execution_report: Artifact
    policy_decisions: Sequence[PolicyDecision]
    start_time: datetime
    end_time: datetime


class ControllerCycle:
    def __init__(
        self,
        bundle_path: Path | str,
        *,
        mode: str = "live",
        dry_run: bool = False,
        report_path: Path | str,
        record_path: Path | str | None = None,
        artifact_output_dir: Path | str | None = None,
        registry: ArtifactRegistry | None = None,
        llm_config: LlmConfigEntry | None = None,
        approval_token: str | None = None,
        run_reliability: RunReliabilityController | None = None,
    ):
        self.bundle_path = Path(bundle_path)
        self.mode = mode
        self.dry_run = dry_run
        self.report_path = Path(report_path)
        self.record_path = (
            Path(record_path) if record_path is not None else Path(".tracemind/controller_decide_records.json")
        )
        self.artifact_output_dir = (
            Path(artifact_output_dir)
            if artifact_output_dir is not None
            else self.report_path.parent / "controller_artifacts"
        )
        self.registry = registry or default_artifact_registry()
        self.agent_registry = default_agent_registry()
        self._policy_guard = PolicyGuard()
        self.bundle_artifact_id: str | None = None
        self.approval_token = approval_token
        self.llm_config = llm_config
        self._reliability = run_reliability or RunReliabilityController(run_id="local")

    def run(self) -> ControllerCycleResult:
        start_time = datetime.now(timezone.utc)
        try:
            bundle = self._load_bundle()
            result = self._execute(bundle, start_time)
            self._reliability.mark_finished(True)
            return result
        except ControllerCycleError as exc:
            self._reliability.mark_finished(False, exc.errors)
            raise
        except Exception as exc:  # pragma: no cover - unexpected errors wrapped
            self._reliability.mark_finished(False, [str(exc)])
            raise ControllerCycleError("controller cycle failed", errors=[str(exc)]) from exc

    def _load_bundle(self) -> Artifact:
        if not self.bundle_path.exists():
            raise ControllerCycleError(f"bundle not found: {self.bundle_path}")
        try:
            from tm.artifacts import load_yaml_artifact

            artifact = load_yaml_artifact(self.bundle_path)
        except Exception as exc:
            raise ControllerCycleError(f"failed to load bundle: {exc}") from exc
        if artifact.envelope.status != ArtifactStatus.ACCEPTED:
            raise ControllerCycleError("bundle artifact must be accepted")
        if artifact.envelope.artifact_type != ArtifactType.AGENT_BUNDLE:
            raise ControllerCycleError("expected agent bundle artifact")
        if not isinstance(artifact.body, AgentBundleBody):
            raise ControllerCycleError("invalid agent bundle body")
        self.bundle_artifact_id = artifact.envelope.artifact_id
        return artifact

    def _execute(self, bundle: Artifact, start_time: datetime) -> ControllerCycleResult:
        context = ExecutionContext()
        bundle_body = bundle.body
        if not isinstance(bundle_body, AgentBundleBody):
            raise ControllerCycleError("invalid agent bundle body")
        bundle_meta = bundle_body.meta if isinstance(bundle_body.meta, Mapping) else {}
        self._reliability.set_profile(ReliabilityProfile.from_meta(bundle_meta))
        self._reliability.mark_bundle(bundle.envelope.artifact_id)
        self._reliability.mark_started()
        agents_by_id = {agent.spec.agent_id: agent for agent in bundle_body.agents}
        configs = self._build_agent_configs()
        snapshot_payload: Mapping[str, Any] | None = None
        plan_artifact: Artifact | None = None
        execution_artifact: Artifact | None = None
        policy_decisions: list[PolicyDecision] = []
        for step in bundle_body.plan:
            agent_entry = agents_by_id.get(step.agent_id)
            if agent_entry is None:
                raise ControllerCycleError(f"unregistered agent '{step.agent_id}' in plan")
            config = configs.get(agent_entry.spec.agent_id, {})
            outputs = self._execute_step(step, agent_entry, config, context)
            if "state:env.snapshot" in outputs:
                snapshot_payload = outputs["state:env.snapshot"]
            if "artifact:proposed.plan" in outputs:
                plan_artifact = self._accept_plan(outputs["artifact:proposed.plan"])
                self._ensure_plan_approval(plan_artifact, context)
                self._evaluate_policy(plan_artifact, context, bundle_meta)
            if "artifact:execution.report" in outputs:
                execution_artifact = self._accept_execution_report(outputs["artifact:execution.report"])
                break
        if execution_artifact is None:
            raise ControllerCycleError("controller cycle did not produce execution report")
        if plan_artifact is None:
            raise ControllerCycleError("decide agent did not emit proposed change plan")
        if snapshot_payload is None:
            raise ControllerCycleError("observe agent did not emit state:env.snapshot")
        env_snapshot_artifact = self._accept_snapshot(snapshot_payload)
        self._persist_artifact(env_snapshot_artifact, "env_snapshot.yaml")
        self._persist_artifact(plan_artifact, "proposed_change_plan.yaml")
        self._persist_artifact(execution_artifact, "execution_report.yaml")
        end_time = datetime.now(timezone.utc)
        return ControllerCycleResult(
            bundle_artifact_id=bundle.envelope.artifact_id,
            env_snapshot=env_snapshot_artifact,
            planned_change=plan_artifact,
            execution_report=execution_artifact,
            policy_decisions=policy_decisions,
            start_time=start_time,
            end_time=end_time,
        )

    def _execute_step(
        self,
        step: AgentBundlePlanStep,
        agent_entry: AgentBundleAgent,
        config: Mapping[str, object],
        context: ExecutionContext,
    ) -> Mapping[str, Any]:
        inputs = _collect_inputs(step, context)
        policy = self._reliability.profile.policy_for_step(step.step)
        outputs: Mapping[str, Any] | None = None
        success_agent: RuntimeAgent | None = None
        for attempt in range(1, policy.max_attempts + 1):
            self._reliability.mark_attempt(step.step, attempt)
            if self._reliability.is_cancelled():
                self._record_cancel_evidence(context, step.step, attempt)
                raise ControllerCycleError("controller cycle cancelled", errors=["run cancelled"])
            runtime_agent = self.agent_registry.resolve(agent_entry.spec.agent_id, agent_entry.spec, config)
            runtime_agent.init({"step": step.step})
            try:
                outputs = run_with_timeout(
                    lambda: context.run_idempotent(
                        f"{runtime_agent.spec.agent_id}:{step.step}",
                        lambda: runtime_agent.run(inputs),
                    ),
                    policy.timeout_seconds,
                )
                success_agent = runtime_agent
                break
            except StepTimeoutError as exc:
                runtime_agent.finalize()
                self._reliability.mark_timeout(step.step, attempt, policy.timeout_seconds, str(exc))
                self._record_timeout_evidence(context, step.step, attempt, policy.timeout_seconds, str(exc))
                if attempt >= policy.max_attempts:
                    errors = [f"agent '{runtime_agent.spec.agent_id}' timed out during step '{step.step}'"]
                    self._reliability.mark_failed(errors[-1])
                    raise ControllerCycleError(
                        f"agent '{runtime_agent.spec.agent_id}' timed out",
                        errors=errors,
                    ) from exc
                self._record_retry_evidence(context, step.step, attempt, str(exc))
                continue
            except Exception as exc:
                runtime_agent.finalize()
                raise ControllerCycleError(
                    f"agent '{runtime_agent.spec.agent_id}' failed during step '{step.step}'",
                    errors=[str(exc)],
                ) from exc
        if success_agent is None or outputs is None:
            raise ControllerCycleError("agent did not complete successfully", errors=["retry failed"])
        agent_evidence = success_agent.state.metadata.get("agent_evidence", [])
        success_agent.finalize()
        metadata = context.metadata
        metadata.setdefault("executed_steps", []).append(step.step)
        step_outputs = metadata.setdefault("step_outputs", {})
        step_outputs[step.step] = {ref: outputs.get(ref) for ref in step.outputs}
        for entry in agent_evidence:
            context.evidence.record(entry["kind"], entry["payload"])
        extra_evidence = success_agent.state.metadata.pop("agent_evidence", [])
        for entry in extra_evidence:
            context.evidence.record(entry["kind"], entry["payload"])
        _persist_outputs(step, context, outputs)
        return outputs

    def _record_timeout_evidence(
        self, context: ExecutionContext, step_name: str, attempt: int, timeout_seconds: float | None, reason: str
    ) -> None:
        context.evidence.record(
            "reliability.timeout",
            {
                "run_id": self._reliability.state.run_id,
                "step": step_name,
                "attempt": attempt,
                "timeout_seconds": timeout_seconds,
                "reason": reason,
            },
        )

    def _record_retry_evidence(self, context: ExecutionContext, step_name: str, attempt: int, reason: str) -> None:
        context.evidence.record(
            "reliability.retry",
            {
                "run_id": self._reliability.state.run_id,
                "step": step_name,
                "attempt": attempt,
                "reason": reason,
            },
        )

    def _record_cancel_evidence(self, context: ExecutionContext, step_name: str, attempt: int) -> None:
        context.evidence.record(
            "reliability.cancel",
            {
                "run_id": self._reliability.state.run_id,
                "step": step_name,
                "attempt": attempt,
                "message": "cancellation requested",
            },
        )

    def _build_agent_configs(self) -> dict[str, Mapping[str, object]]:
        configs: dict[str, Mapping[str, object]] = {}
        decide_config: dict[str, object] = {
            "mode": self.mode,
            "record_path": str(self.record_path),
        }
        if self.llm_config is not None:
            decide_config.update(
                {
                    "model": self.llm_config.model,
                    "model_id": self.llm_config.model_id,
                    "model_version": self.llm_config.model_version,
                    "prompt_template_version": self.llm_config.prompt_template_version,
                    "prompt_version": self.llm_config.prompt_version,
                    "llm_config_id": self.llm_config.config_id,
                }
            )
        configs[DecideAgent.AGENT_ID] = decide_config
        return configs

    def _accept_snapshot(self, payload: Mapping[str, Any]) -> Artifact:
        envelope = self._build_envelope(ArtifactType.ENVIRONMENT_SNAPSHOT, "env_snapshot")
        body = EnvSnapshotBody.from_mapping(payload)
        artifact = Artifact(envelope=envelope, body=body, body_raw=dict(payload))
        return self._verify(artifact)

    def _accept_plan(self, payload: Mapping[str, Any]) -> Artifact:
        envelope = self._build_envelope(ArtifactType.PROPOSED_CHANGE_PLAN, "proposed_change_plan")
        body = ProposedChangePlanBody.from_mapping(payload)
        artifact = Artifact(envelope=envelope, body=body, body_raw=dict(payload))
        return self._verify(artifact)

    def _accept_execution_report(self, payload: Mapping[str, Any]) -> Artifact:
        envelope = self._build_envelope(ArtifactType.EXECUTION_REPORT, "execution_report")
        body = ExecutionReportBody.from_mapping(payload)
        artifact = Artifact(envelope=envelope, body=body, body_raw=dict(payload))
        return self._verify(artifact)

    def _verify(self, artifact: Artifact) -> Artifact:
        accepted, report = verify(artifact)
        if accepted is None:
            raise ControllerCycleError("artifact verification failed", errors=report.errors)
        return accepted

    def _evaluate_policy(
        self,
        plan_artifact: Artifact,
        context: ExecutionContext,
        bundle_meta: Mapping[str, Any],
    ) -> list[PolicyDecision]:
        body = plan_artifact.body
        if not isinstance(body, ProposedChangePlanBody):
            raise ControllerCycleError("invalid proposed change plan artifact")
        guard = self._policy_guard
        decisions: list[PolicyDecision] = []
        requirements = body.policy_requirements or []
        for target in requirements:
            effect = EffectRef(
                name=target,
                kind="resource",
                target=target,
                idempotency=EffectIdempotency(type="keyed", key_fields=[]),
                rollback=None,
                evidence={"type": "hash"},
            )
            decision = guard.evaluate(effect, context, bundle_meta)
            decisions.append(decision)
            if not decision.allowed:
                raise ControllerCycleError(
                    f"policy guard denied '{target}'",
                    errors=[
                        f"policy guard denied '{target}'",
                        f"{decision.effect_name}: {decision.reason}",
                    ],
                )
        return decisions

    def _ensure_plan_approval(self, plan_artifact: Artifact, context: ExecutionContext) -> None:
        if not self._plan_requires_approval(plan_artifact):
            return
        if not self._is_approved():
            raise ControllerCycleError(
                "resource effects require explicit approval",
                errors=["plan requires approval before executing resource effects"],
            )
        if self.approval_token:
            context.metadata.setdefault("approval_token", self.approval_token)

    def _plan_requires_approval(self, plan_artifact: Artifact) -> bool:
        if self.dry_run:
            return False
        body = plan_artifact.body
        if not isinstance(body, ProposedChangePlanBody):
            return False
        for decision in body.decisions:
            if isinstance(decision.effect_ref, str) and decision.effect_ref.startswith("resource:"):
                return True
        return False

    def _is_approved(self) -> bool:
        return isinstance(self.approval_token, str) and self.approval_token.startswith("approved")

    def _persist_artifact(self, artifact: Artifact, filename: str) -> None:
        doc = _artifact_document(artifact)
        target = self.artifact_output_dir / filename
        _write_doc(target, doc)
        if self.dry_run:
            return
        self.registry.add(artifact, target)

    def _build_envelope(self, artifact_type: ArtifactType, suffix: str) -> ArtifactEnvelope:
        artifact_id = f"tm-controller/{suffix}-{_slug(self.bundle_path.stem)}"
        return ArtifactEnvelope(
            artifact_id=artifact_id,
            status=ArtifactStatus.CANDIDATE,
            artifact_type=artifact_type,
            version="v0",
            created_by="controller.cycle",
            created_at=_iso_now(),
            body_hash="",
            envelope_hash="",
            meta={
                "phase": "controller-cycle",
                "bundle": str(self.bundle_path),
                "mode": self.mode,
            },
        )
