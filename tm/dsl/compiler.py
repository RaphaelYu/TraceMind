from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]

from .compiler_flow import FlowCompilation, FlowCompileError, compile_workflow
from .compiler_policy import PolicyCompileError, compile_policy
from .ir import WdlTrigger, parse_pdl_document, parse_wdl_document
from .lint import lint_paths


class CompileError(RuntimeError):
    """Raised when compilation fails."""


@dataclass(frozen=True)
class CompiledArtifact:
    source: Path
    kind: str  # "flow" | "policy"
    identifier: str
    output: Path


def compile_paths(
    paths: Sequence[Path],
    *,
    out_dir: Path,
    force: bool = False,
    run_lint: bool = True,
) -> List[CompiledArtifact]:
    files = tuple(_discover_files(paths))
    if not files:
        raise CompileError("No DSL files found for compilation")

    if run_lint:
        issues = lint_paths(files)
        errors = [issue for issue in issues if issue.level == "error"]
        if errors:
            summary = "\n".join(f"{issue.path}:{issue.line}:{issue.column}: {issue.message}" for issue in errors)
            raise CompileError(f"Lint failures prevent compilation:\n{summary}")

    out_dir = out_dir.resolve()
    flows_dir = out_dir / "flows"
    policies_dir = out_dir / "policies"
    flows_dir.mkdir(parents=True, exist_ok=True)
    policies_dir.mkdir(parents=True, exist_ok=True)

    policy_map: dict[str, CompiledArtifact] = {}
    artifacts: List[CompiledArtifact] = []
    trigger_entries: List[dict[str, object]] = []
    used_trigger_ids: set[str] = set()

    # Compile policies first so flows can reference them.
    for path in files:
        if path.suffix.lower() == ".pdl":
            artifact = _compile_pdl(path, policies_dir, force=force)
            policy_map[path.stem] = artifact
            artifacts.append(artifact)

    for path in files:
        if path.suffix.lower() == ".wdl":
            artifact = _compile_wdl(
                path,
                flows_dir,
                policy_map=policy_map,
                force=force,
                trigger_entries=trigger_entries,
                used_trigger_ids=used_trigger_ids,
            )
            artifacts.append(artifact)

    if trigger_entries:
        triggers_path = out_dir / "triggers.yaml"
        if triggers_path.exists() and not force:
            raise CompileError(f"Output file '{triggers_path}' already exists (use --force to overwrite)")
        _write_yaml(triggers_path, {"triggers": trigger_entries})
        artifacts.append(
            CompiledArtifact(
                source=out_dir,
                kind="trigger",
                identifier="triggers",
                output=triggers_path,
            )
        )

    return artifacts


def _discover_files(paths: Sequence[Path]) -> Iterable[Path]:
    seen: dict[Path, None] = {}
    for candidate in paths:
        if candidate.is_file():
            if candidate.suffix.lower() in {".wdl", ".pdl"}:
                seen.setdefault(candidate.resolve(), None)
        elif candidate.is_dir():
            for nested in candidate.rglob("*"):
                if nested.is_file() and nested.suffix.lower() in {".wdl", ".pdl"}:
                    seen.setdefault(nested.resolve(), None)
    return sorted(seen.keys())


def _compile_wdl(
    path: Path,
    out_dir: Path,
    *,
    policy_map: dict[str, CompiledArtifact],
    force: bool,
    trigger_entries: List[dict[str, object]],
    used_trigger_ids: set[str],
) -> CompiledArtifact:
    try:
        workflow = parse_wdl_document(path.read_text(encoding="utf-8"), filename=str(path))
        compilation = compile_workflow(workflow, source=path)
    except FlowCompileError as exc:
        raise CompileError(f"{path}: {exc}") from exc
    except Exception as exc:
        raise CompileError(f"{path}: {exc}") from exc
    file_name = f"{_slugify(compilation.flow_id)}.yaml"
    output_path = out_dir / file_name
    policy_artifact = policy_map.get(path.stem)
    if policy_artifact is not None:
        _attach_policy_reference(compilation, policy_artifact)
    trigger_entries.extend(_collect_triggers(workflow, compilation.flow_id, path, used_trigger_ids))
    if output_path.exists() and not force:
        raise CompileError(f"Output file '{output_path}' already exists (use --force to overwrite)")
    _write_yaml(output_path, compilation.data)
    return CompiledArtifact(source=path, kind="flow", identifier=compilation.flow_id, output=output_path)


def _compile_pdl(path: Path, out_dir: Path, *, force: bool) -> CompiledArtifact:
    try:
        policy = parse_pdl_document(path.read_text(encoding="utf-8"), filename=str(path))
        compilation = compile_policy(policy, source=path)
    except PolicyCompileError as exc:
        raise CompileError(f"{path}: {exc}") from exc
    except Exception as exc:
        raise CompileError(f"{path}: {exc}") from exc
    file_name = f"{_slugify(compilation.policy_id)}.json"
    output_path = out_dir / file_name
    if output_path.exists() and not force:
        raise CompileError(f"Output file '{output_path}' already exists (use --force to overwrite)")
    output_path.write_text(json.dumps(compilation.data, indent=2), encoding="utf-8")
    return CompiledArtifact(source=path, kind="policy", identifier=compilation.policy_id, output=output_path)


def _write_yaml(path: Path, data: object) -> None:
    if yaml is None:
        raise CompileError("PyYAML is required to write flow YAML. Install the 'yaml' extra.")
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def _slugify(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "-", name)
    safe = safe.strip("-")
    return safe or "flow"


def _attach_policy_reference(compilation: FlowCompilation, artifact: CompiledArtifact) -> None:
    flow = compilation.data.get("flow")
    if not isinstance(flow, dict):
        return
    steps = flow.get("steps")
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        config = step.get("config")
        if not isinstance(config, dict):
            continue
        call = config.get("call")
        if not isinstance(call, dict):
            continue
        target = call.get("target")
        if isinstance(target, str) and target.startswith("policy."):
            config["policy_ref"] = str(artifact.output)
            config["policy_id"] = artifact.identifier


def _collect_triggers(
    workflow,
    flow_id: str,
    source_path: Path,
    used_ids: set[str],
) -> List[dict[str, object]]:
    entries: List[dict[str, object]] = []
    for index, trigger in enumerate(workflow.triggers, start=1):
        entry = _trigger_to_config(trigger, flow_id, index, source_path, used_ids)
        if entry is not None:
            entries.append(entry)
    return entries


def _trigger_to_config(
    trigger: WdlTrigger,
    flow_id: str,
    index: int,
    source_path: Path,
    used_ids: set[str],
) -> dict[str, object] | None:
    trigger_type = trigger.trigger_type.lower()
    mapped_kind = _map_trigger_kind(trigger_type, trigger, source_path)
    if mapped_kind is None:
        return None

    config = dict(trigger.config)
    trigger_id = str(config.pop("id", "")).strip() or f"{flow_id}-{trigger_type}-{index}"
    if trigger_id in used_ids:
        raise CompileError(
            f"{source_path}:{trigger.location.line}:{trigger.location.column}: duplicate trigger id '{trigger_id}'"
        )
    used_ids.add(trigger_id)

    target_flow_id = str(config.pop("flow_id", config.pop("flow", flow_id)))
    input_template = config.pop("input", config.pop("input_template", {}))
    if not isinstance(input_template, dict):
        raise CompileError(
            f"{source_path}:{trigger.location.line}:{trigger.location.column}: trigger input must be an object"
        )
    idempotency_key = config.pop("idempotency_key", None)

    type_specific = _map_trigger_fields(mapped_kind, config, trigger, source_path)

    entry: dict[str, object] = {
        "id": trigger_id,
        "kind": mapped_kind,
        "flow_id": target_flow_id,
    }
    if input_template:
        entry["input"] = input_template
    if idempotency_key:
        entry["idempotency_key"] = idempotency_key
    entry.update(type_specific)
    return entry


def _map_trigger_kind(trigger_type: str, trigger: WdlTrigger, source_path: Path) -> str:
    if trigger_type == "cron":
        return "cron"
    if trigger_type in {"http", "webhook"}:
        return "webhook"
    if trigger_type in {"fs", "filesystem"}:
        return "filesystem"
    raise CompileError(
        f"{source_path}:{trigger.location.line}:{trigger.location.column}: unsupported trigger type '{trigger.trigger_type}'"
    )


def _map_trigger_fields(
    kind: str,
    config: dict[str, object],
    trigger: WdlTrigger,
    source_path: Path,
) -> dict[str, object]:
    if kind == "cron":
        cron_expr = config.pop("cron", config.pop("schedule", None))
        if not isinstance(cron_expr, str) or not cron_expr.strip():
            raise CompileError(
                f"{source_path}:{trigger.location.line}:{trigger.location.column}: cron trigger requires 'schedule'"
            )
        entry = {"cron": cron_expr.strip()}
        timezone = config.pop("timezone", None)
        if isinstance(timezone, str) and timezone.strip():
            entry["timezone"] = timezone.strip()
        entry.update(config)
        return entry

    if kind == "webhook":
        route = config.pop("route", config.pop("path", None))
        if not isinstance(route, str) or not route.strip():
            raise CompileError(
                f"{source_path}:{trigger.location.line}:{trigger.location.column}: webhook trigger requires 'route'"
            )
        method = config.pop("method", "POST")
        if isinstance(method, str):
            method = method.upper()
        entry = {"route": route, "method": method}
        entry.update(config)
        return entry

    if kind == "filesystem":
        path_value = config.pop("path", None)
        if not isinstance(path_value, str) or not path_value.strip():
            raise CompileError(
                f"{source_path}:{trigger.location.line}:{trigger.location.column}: filesystem trigger requires 'path'"
            )
        entry = {"path": path_value}
        entry.update(config)
        return entry

    return config


__all__ = ["CompileError", "CompiledArtifact", "compile_paths"]
