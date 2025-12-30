"""Controller-themed FastAPI routes for running TraceMind cycles over HTTP."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from tm.artifacts.models import ArtifactType
from tm.artifacts.registry import ArtifactRegistry, RegistryEntry
from tm.artifacts.storage import RegistryStorage
from tm.controllers.cycle import (
    ControllerCycle,
    ControllerCycleError,
    ControllerCycleResult,
    write_gap_and_backlog,
)
from tm.server.config import ServerConfig
from tm.utils.yaml import import_yaml

yaml = import_yaml()


class CycleRunRequest(BaseModel):
    bundle_artifact_id: str
    mode: str = "live"
    dry_run: bool = False
    run_id: str | None = None


class CycleRunResponse(BaseModel):
    run_id: str
    report_path: str
    success: bool
    errors: List[str]
    gap_map: str | None
    backlog: str | None
    report: Dict[str, Any]


class ArtifactDiffRequest(BaseModel):
    base_id: str
    compare_id: str


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in normalized)
    return "-".join(part for part in cleaned.split("-") if part)


def _make_run_id(bundle_id: str, override: str | None) -> str:
    candidate = _slug(override or bundle_id)
    if not candidate:
        candidate = "cycle"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{candidate}-{timestamp}"


def _write_document(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=True, allow_unicode=True)
        return
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_document(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, Mapping):
        raise ValueError(f"expected mapping document at {path}")
    return dict(data)


def _format_path(path: Tuple[Any, ...]) -> str:
    parts: list[str] = []
    for part in path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        else:
            parts.append(str(part))
    return ".".join(parts)


def _diff_json(old: Any, new: Any, path: Tuple[Any, ...] = ()) -> List[Tuple[Tuple[Any, ...], str, Any, Any]]:
    diffs: List[Tuple[Tuple[Any, ...], str, Any, Any]] = []
    if isinstance(old, dict) and isinstance(new, dict):
        keys = sorted(set(old.keys()) | set(new.keys()))
        for key in keys:
            a = old.get(key)
            b = new.get(key)
            if key not in old:
                diffs.append((path + (key,), "added", None, b))
            elif key not in new:
                diffs.append((path + (key,), "removed", a, None))
            else:
                diffs.extend(_diff_json(a, b, path + (key,)))
        return diffs
    if isinstance(old, list) and isinstance(new, list):
        length = max(len(old), len(new))
        for index in range(length):
            if index >= len(old):
                diffs.append((path + (index,), "added", None, new[index]))
            elif index >= len(new):
                diffs.append((path + (index,), "removed", old[index], None))
            else:
                diffs.extend(_diff_json(old[index], new[index], path + (index,)))
        return diffs
    if old != new:
        diffs.append((path, "modified", old, new))
    return diffs


def _read_artifact_document(entry: RegistryEntry) -> Dict[str, Any]:
    path = Path(entry.path)
    if not path.exists():
        alt = Path.cwd() / entry.path
        if alt.exists():
            path = alt
        else:
            raise FileNotFoundError(entry.path)
    return _load_document(path)


def _build_success_payload(
    result: ControllerCycleResult,
    run_id: str,
    mode: str,
    dry_run: bool,
    artifact_dir: Path,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": mode,
        "dry_run": dry_run,
        "success": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_artifact_id": result.bundle_artifact_id,
        "env_snapshot": result.env_snapshot.envelope.artifact_id,
        "proposed_change_plan": result.planned_change.envelope.artifact_id,
        "execution_report": result.execution_report.envelope.artifact_id,
        "start_time": result.start_time.isoformat(),
        "end_time": result.end_time.isoformat(),
        "duration_seconds": (result.end_time - result.start_time).total_seconds(),
        "policy_decisions": [
            {
                "effect": decision.effect_name,
                "target": decision.target,
                "allowed": decision.allowed,
                "reason": decision.reason,
            }
            for decision in result.policy_decisions
        ],
        "errors": [],
        "artifact_output_dir": str(artifact_dir),
    }


def _build_failure_payload(
    bundle_id: str,
    run_id: str,
    mode: str,
    dry_run: bool,
    errors: Sequence[str],
    gap_map: Path | None,
    backlog: Path | None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "dry_run": dry_run,
        "success": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bundle_artifact_id": bundle_id,
        "errors": list(errors),
    }
    if gap_map is not None:
        payload["gap_map"] = str(gap_map)
    if backlog is not None:
        payload["backlog"] = str(backlog)
    return payload


def create_controller_router(config: ServerConfig) -> APIRouter:
    storage = RegistryStorage(config.registry_path)
    registry = ArtifactRegistry(storage)
    router = APIRouter(prefix="/api/controller", tags=["controller"])

    @router.get("/bundles")
    def list_bundles() -> List[Dict[str, Any]]:
        entries = registry.list_by_type(ArtifactType.AGENT_BUNDLE)
        return [entry.to_dict() for entry in entries]

    @router.get("/artifacts")
    def list_artifacts(
        intent_id: str | None = None,
        body_hash: str | None = None,
        artifact_type: str | None = None,
    ) -> List[Dict[str, Any]]:
        entries = registry.list_all()
        if artifact_type:
            try:
                target = ArtifactType(artifact_type)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                )
            entries = [entry for entry in entries if entry.artifact_type == target]
        if intent_id:
            entries = [entry for entry in entries if entry.intent_id == intent_id]
        if body_hash:
            entries = [entry for entry in entries if entry.body_hash == body_hash]
        return [entry.to_dict() for entry in entries]

    @router.get("/artifacts/{artifact_id}")
    def get_artifact(artifact_id: str) -> Dict[str, Any]:
        entry = registry.get_by_artifact_id(artifact_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
        try:
            document = _read_artifact_document(entry)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        return {"entry": entry.to_dict(), "document": document}

    @router.post("/artifacts/diff")
    def diff_artifacts(payload: ArtifactDiffRequest) -> Dict[str, Any]:
        entry_a = registry.get_by_artifact_id(payload.base_id)
        entry_b = registry.get_by_artifact_id(payload.compare_id)
        if entry_a is None or entry_b is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
        doc_a = _read_artifact_document(entry_a)
        doc_b = _read_artifact_document(entry_b)
        changes = _diff_json(doc_a, doc_b)
        formatted = [
            {
                "path": _format_path(path),
                "kind": kind,
                "base": base,
                "compare": compare,
            }
            for path, kind, base, compare in changes
        ]
        return {
            "base_id": payload.base_id,
            "compare_id": payload.compare_id,
            "diff": formatted,
        }

    @router.get("/reports")
    def list_reports() -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for run_dir in sorted(config.runs_dir_path.iterdir()):
            if not run_dir.is_dir():
                continue
            report_path = run_dir / "cycle_report.yaml"
            if not report_path.exists():
                continue
            try:
                report = _load_document(report_path)
            except (FileNotFoundError, ValueError):
                continue
            runs.append(
                {
                    "run_id": run_dir.name,
                    "report": report,
                    "report_path": str(report_path),
                    "gap_map": str(run_dir / "gap_map.yaml") if (run_dir / "gap_map.yaml").exists() else None,
                    "backlog": str(run_dir / "backlog.yaml") if (run_dir / "backlog.yaml").exists() else None,
                }
            )
        return runs

    @router.get("/reports/{run_id}")
    def get_report(run_id: str) -> Dict[str, Any]:
        report_path = config.runs_dir_path / run_id / "cycle_report.yaml"
        if not report_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
        return _load_document(report_path)

    @router.post("/cycle")
    def run_cycle(request: CycleRunRequest) -> CycleRunResponse:
        entry = registry.get_by_artifact_id(request.bundle_artifact_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bundle not registered")
        try:
            bundle_path = Path(entry.path)
            if not bundle_path.exists():
                alt = Path.cwd() / entry.path
                if alt.exists():
                    bundle_path = alt
                else:
                    raise FileNotFoundError(entry.path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        run_id = _make_run_id(entry.artifact_id, request.run_id)
        run_dir = config.runs_dir_path / run_id
        artifact_dir = run_dir / "controller_artifacts"
        report_path = run_dir / "cycle_report.yaml"
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        runner = ControllerCycle(
            bundle_path=bundle_path,
            mode=request.mode,
            dry_run=request.dry_run,
            report_path=report_path,
            record_path=config.record_path,
            artifact_output_dir=artifact_dir,
            registry=registry,
        )
        errors: List[str] = []
        gap_map: Path | None = None
        backlog: Path | None = None
        payload: Dict[str, Any]
        try:
            result = runner.run()
            payload = _build_success_payload(result, run_id, request.mode, request.dry_run, artifact_dir)
        except ControllerCycleError as exc:
            errors = exc.errors
            dependency_id = runner.bundle_artifact_id or entry.artifact_id
            gap_map, backlog = write_gap_and_backlog(report_path, dependency_id, errors)
            payload = _build_failure_payload(
                entry.artifact_id, run_id, request.mode, request.dry_run, errors, gap_map, backlog
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
        finally:
            _write_document(report_path, payload)
        return CycleRunResponse(
            run_id=run_id,
            report_path=str(report_path),
            success=payload.get("success", False),
            errors=errors,
            gap_map=str(gap_map) if gap_map else None,
            backlog=str(backlog) if backlog else None,
            report=payload,
        )

    router.list_bundles = list_bundles  # type: ignore[attr-defined]
    router.list_artifacts = list_artifacts  # type: ignore[attr-defined]
    router.get_artifact = get_artifact  # type: ignore[attr-defined]
    router.diff_artifacts = diff_artifacts  # type: ignore[attr-defined]
    router.list_reports = list_reports  # type: ignore[attr-defined]
    router.get_report = get_report  # type: ignore[attr-defined]
    router.run_cycle = run_cycle  # type: ignore[attr-defined]
    return router
