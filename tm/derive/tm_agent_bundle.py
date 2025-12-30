from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from tm.artifacts import Artifact, load_yaml_artifact, verify
from tm.artifacts.models import IntentBody
from tm.artifacts.report import ArtifactVerificationReport
from tm.artifacts.types import ArtifactType
from tm.utils.yaml import import_yaml

# PyYAML is optional; import_yaml already handles detection and wrapping
yaml = import_yaml()

VerifyFn = Callable[[Artifact], tuple[Artifact | None, ArtifactVerificationReport]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in normalized)
    return "-".join(part for part in cleaned.split("-") if part)


def _build_envelope(
    artifact_id: str,
    artifact_type: str,
    created_at: str,
    phase: str,
    source_id: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "status": "candidate",
        "artifact_type": artifact_type,
        "version": "v0",
        "created_by": "codex-deriver",
        "created_at": created_at,
        "body_hash": "",
        "envelope_hash": "",
        "meta": {
            "phase": phase,
            "derived_from": {"phase": "intent", "intent_id": source_id},
        },
    }


def _write_document(document: Mapping[str, Any], path: Path) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required; install trace-mind[yaml]")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _artifact_to_document(artifact: Artifact) -> dict[str, Any]:
    envelope = asdict(artifact.envelope)
    envelope["status"] = artifact.envelope.status.value
    envelope["artifact_type"] = artifact.envelope.artifact_type.value
    if artifact.envelope.signature is None:
        envelope.pop("signature", None)
    return {"envelope": envelope, "body": dict(artifact.body_raw)}


def _build_candidate_capability(intent: IntentBody, slug: str, created_at: str) -> dict[str, Any]:
    artifact_id = f"tm-capability-derived-{slug}"
    inputs = list(intent.inputs) or ["artifact:input"]
    outputs = list(intent.outputs) or ["artifact:result"]
    constraints = list(intent.constraints) if intent.constraints else ["derived"]
    envelope = _build_envelope(artifact_id, ArtifactType.CAPABILITIES.value, created_at, "derived", intent.intent_id)
    body = {
        "capability_id": f"{slug}.capability",
        "description": intent.goal or "Derived capability",
        "inputs": inputs,
        "outputs": outputs,
        "constraints": constraints,
        "execution_binding": {
            "type": "builtin",
            "ref": "tm.capability.derived_agent_bundle",
            "metadata": {"intent": intent.intent_id},
        },
    }
    return {"envelope": envelope, "body": body}


def _build_candidate_agent_bundle(intent: IntentBody, slug: str, created_at: str) -> dict[str, Any]:
    artifact_id = f"tm-agent-bundle-derived-{slug}"
    envelope = _build_envelope(artifact_id, ArtifactType.AGENT_BUNDLE.value, created_at, "derived", intent.intent_id)
    agents: list[dict[str, Any]] = [
        {
            "agent_id": "tm-agent/noop:0.1",
            "name": f"noop-{slug}",
            "version": "0.1",
            "runtime": {"kind": "tm-noop", "config": {}},
            "contract": {
                "inputs": [
                    {
                        "ref": "artifact:http_request",
                        "kind": "artifact",
                        "schema": {"type": "object"},
                        "required": True,
                        "mode": "read",
                    }
                ],
                "outputs": [
                    {
                        "ref": "state:noop.out",
                        "kind": "resource",
                        "schema": {"type": "object"},
                        "required": False,
                        "mode": "write",
                    }
                ],
                "effects": [
                    {
                        "name": "noop-effect",
                        "kind": "resource",
                        "target": "state:noop.out",
                        "idempotency": {"type": "keyed", "key_fields": ["artifact_id"]},
                        "evidence": {"type": "status"},
                    }
                ],
            },
            "config_schema": {"type": "object"},
            "evidence_outputs": [{"name": "noop-evidence"}],
            "role": "builtin",
        },
        {
            "agent_id": "tm-agent/http-mock:0.1",
            "name": f"http-mock-{slug}",
            "version": "0.1",
            "runtime": {
                "kind": "tm-http-mock",
                "config": {
                    "responses": {
                        "GET https://example.com/api/demo": {
                            "status": 200,
                            "headers": {"x-derived": slug},
                            "body": "ok",
                        }
                    }
                },
            },
            "contract": {
                "inputs": [
                    {
                        "ref": "artifact:http_request",
                        "kind": "artifact",
                        "schema": {"type": "object"},
                        "required": True,
                        "mode": "read",
                    }
                ],
                "outputs": [
                    {
                        "ref": "artifact:http_response",
                        "kind": "artifact",
                        "schema": {"type": "object"},
                        "required": False,
                        "mode": "write",
                    }
                ],
                "effects": [
                    {
                        "name": "respond",
                        "kind": "resource",
                        "target": "artifact:http_response",
                        "idempotency": {"type": "keyed", "key_fields": ["artifact_id"]},
                        "evidence": {"type": "status"},
                    }
                ],
            },
            "config_schema": {"type": "object"},
            "evidence_outputs": [{"name": "http-mock-evidence"}],
            "role": "builtin",
        },
        {
            "agent_id": "tm-agent/shell:0.1",
            "name": f"shell-{slug}",
            "version": "0.1",
            "runtime": {"kind": "tm-shell", "config": {"command": f"echo guard-{slug}"}},
            "contract": {
                "inputs": [],
                "outputs": [
                    {
                        "ref": "state:shell.stdout",
                        "kind": "resource",
                        "schema": {"type": "string"},
                        "required": False,
                        "mode": "write",
                    },
                    {
                        "ref": "state:shell.stderr",
                        "kind": "resource",
                        "schema": {"type": "string"},
                        "required": False,
                        "mode": "write",
                    },
                    {
                        "ref": "state:shell.exit_code",
                        "kind": "resource",
                        "schema": {"type": "integer"},
                        "required": False,
                        "mode": "write",
                    },
                ],
                "effects": [
                    {
                        "name": "report-stdout",
                        "kind": "resource",
                        "target": "state:shell.stdout",
                        "idempotency": {"type": "keyed", "key_fields": ["command"]},
                        "evidence": {"type": "status"},
                    },
                    {
                        "name": "report-stderr",
                        "kind": "resource",
                        "target": "state:shell.stderr",
                        "idempotency": {"type": "keyed", "key_fields": ["command"]},
                        "evidence": {"type": "status"},
                    },
                    {
                        "name": "report-exit",
                        "kind": "resource",
                        "target": "state:shell.exit_code",
                        "idempotency": {"type": "keyed", "key_fields": ["command"]},
                        "evidence": {"type": "status"},
                    },
                ],
            },
            "config_schema": {"type": "object"},
            "evidence_outputs": [{"name": "shell-evidence"}],
            "role": "builtin",
        },
    ]
    plan = [
        {
            "step": f"noop-{slug}",
            "agent_id": "tm-agent/noop:0.1",
            "phase": "run",
            "inputs": ["artifact:http_request"],
            "outputs": ["state:noop.out"],
        },
        {
            "step": f"http-{slug}",
            "agent_id": "tm-agent/http-mock:0.1",
            "phase": "run",
            "inputs": ["artifact:http_request"],
            "outputs": ["artifact:http_response"],
        },
        {
            "step": f"shell-{slug}",
            "agent_id": "tm-agent/shell:0.1",
            "phase": "run",
            "outputs": ["state:shell.stdout", "state:shell.stderr", "state:shell.exit_code"],
        },
    ]
    body = {
        "bundle_id": f"tm-bundle/derived-{slug}",
        "agents": agents,
        "plan": plan,
        "meta": {
            "preconditions": ["artifact:http_request"],
            "policy": {"allow": ["state:noop.out", "artifact:http_response"]},
        },
    }
    return {"envelope": envelope, "body": body}


def _build_gap_map(intent: IntentBody, intent_slug: str, errors: Sequence[str], created_at: str) -> dict[str, Any]:
    artifact_id = f"tm-gap-map-derived-{intent_slug}"
    envelope = _build_envelope(artifact_id, ArtifactType.GAP_MAP.value, created_at, "derived", intent.intent_id)
    description = (
        "Candidate derivation detected gaps: " + "; ".join(errors)
        if errors
        else "Candidate derivation succeeded without blocking gaps."
    )
    mitigations = list(errors) if errors else ["No additional mitigation required."]
    severity = "high" if errors else "low"
    body = {
        "gap_id": f"gap-{intent_slug}",
        "gap_description": description,
        "impacted_intents": [intent.intent_id],
        "mitigations": mitigations,
        "severity": severity,
    }
    return {"envelope": envelope, "body": body}


def _build_backlog(intent: IntentBody, intent_slug: str, errors: Sequence[str], created_at: str) -> dict[str, Any]:
    artifact_id = f"tm-backlog-derived-{intent_slug}"
    envelope = _build_envelope(artifact_id, ArtifactType.BACKLOG.value, created_at, "derived", intent.intent_id)
    description = "Resolve: " + "; ".join(errors) if errors else f"Review derived bundle for intent {intent.intent_id}."
    priority = "high" if errors else "low"
    body = {
        "backlog_id": f"backlog-{intent_slug}",
        "items": [
            {
                "intent_id": intent.intent_id,
                "priority": priority,
                "description": description,
            }
        ],
    }
    return {"envelope": envelope, "body": body}


def derive_from_intent(
    intent_path: Path,
    out_dir: Path,
    *,
    verify_fn: VerifyFn | None = None,
) -> bool:
    if verify_fn is None:
        verify_fn = verify
    intent_artifact = load_yaml_artifact(intent_path)
    if not isinstance(intent_artifact.body, IntentBody):
        raise ValueError("derived artifact must point to an intent candidate")
    intent = intent_artifact.body
    slug = _slug(intent.intent_id)
    created_at = _now_iso()
    capability_doc = _build_candidate_capability(intent, slug, created_at)
    bundle_doc = _build_candidate_agent_bundle(intent, slug, created_at)
    candidates = [("capabilities", capability_doc), ("agent_bundle", bundle_doc)]
    errors: list[str] = []
    success = True
    for name, document in candidates:
        candidate_path = out_dir / f"{name}_candidate.yaml"
        _write_document(document, candidate_path)
        artifact = load_yaml_artifact(candidate_path)
        accepted, report = verify_fn(artifact)
        errors.extend(report.errors)
        if accepted is None or not report.success:
            success = False
            continue
        accepted_path = out_dir / f"{name}_accepted.yaml"
        _write_document(_artifact_to_document(accepted), accepted_path)
    gap_map_doc = _build_gap_map(intent, slug, errors, created_at)
    backlog_doc = _build_backlog(intent, slug, errors, created_at)
    _write_document(gap_map_doc, out_dir / "gap_map.yaml")
    _write_document(backlog_doc, out_dir / "backlog.yaml")
    print(f"Derived artifacts written to {out_dir}")
    return success


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Derive an agent bundle from an intent candidate.")
    parser.add_argument("--intent", type=Path, required=True, help="Intent candidate artifact path.")
    parser.add_argument("--out", type=Path, default=Path("derived"), help="Directory to write derived artifacts.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    success = derive_from_intent(args.intent, args.out)
    json_obj: dict[str, Any] = {"intent": str(args.intent), "output_dir": str(args.out), "success": success}
    print(json.dumps(json_obj, indent=2))
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
