"""Regression tests for the TraceMind TM server workspace and controller APIs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import httpx
from tm.artifacts import Artifact
from tm.artifacts.registry import ArtifactRegistry, RegistryStorage
from tm.server.app import create_app
from tm.utils.yaml import import_yaml

from tests.test_controller_demo_bundle_v0 import _build_controller_bundle

yaml = import_yaml()


def _artifact_document(artifact: Artifact) -> dict[str, object]:
    envelope = asdict(artifact.envelope)
    envelope["status"] = artifact.envelope.status.value
    envelope["artifact_type"] = artifact.envelope.artifact_type.value
    if artifact.envelope.signature is None:
        envelope.pop("signature", None)
    return {"envelope": envelope, "body": dict(artifact.body_raw)}


def _write_document(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, sort_keys=True, allow_unicode=True)
        return
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")


def _register_controller_bundle(artifacts_root: Path) -> Artifact:
    bundle = _build_controller_bundle(["state:env.snapshot", "artifact:proposed.plan", "resource:inventory:update"])
    bundle_path = artifacts_root / "controller_bundle.yaml"
    _write_document(bundle_path, _artifact_document(bundle))
    storage = RegistryStorage(artifacts_root / "registry.jsonl")
    ArtifactRegistry(storage).add(bundle, bundle_path)
    return bundle


def _workspace_manifest_path(workspace_root: Path) -> Path:
    return workspace_root / "tracemind.workspace.yaml"


async def test_tm_server_workspace_controller_flow(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    manifest_path = _workspace_manifest_path(workspace_root)
    _write_document(manifest_path, {"workspace_id": "tm-workspace:///controller", "name": "controller-test"})

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        mount_response = await client.post("/api/v1/workspaces/mount", json={"path": str(workspace_root)})
        mount_response.raise_for_status()
        mounted = mount_response.json()
        workspace_id = mounted["workspace_id"]
        artifacts_dir = Path(mounted["directories"]["artifacts"])
        specs_dir = Path(mounted["directories"]["specs"])
        assert artifacts_dir == (workspace_root / ".tracemind").resolve()
        assert specs_dir == (workspace_root / "specs").resolve()

        params = {"workspace_id": workspace_id}
        bundle = _register_controller_bundle(artifacts_dir)

        bundles = (await client.get("/api/controller/bundles", params=params)).json()
        assert any(entry["artifact_id"] == bundle.envelope.artifact_id for entry in bundles)

        artifacts = (await client.get("/api/controller/artifacts", params=params)).json()
        assert any(entry["artifact_id"] == bundle.envelope.artifact_id for entry in artifacts)

        detail = (await client.get(f"/api/controller/artifacts/{bundle.envelope.artifact_id}", params=params)).json()
        print(f"result={detail} from /api/controller/artifacts/{bundle.envelope.artifact_id}")
        assert detail["entry"]["artifact_id"] == bundle.envelope.artifact_id
        assert detail["document"]["envelope"]["artifact_id"] == bundle.envelope.artifact_id

        diff_payload = {"base_id": bundle.envelope.artifact_id, "compare_id": bundle.envelope.artifact_id}
        diff = await client.post("/api/controller/artifacts/diff", params=params, json=diff_payload)
        diff_data = diff.json()
        assert diff_data["base_id"] == bundle.envelope.artifact_id
        assert diff_data["diff"] == []

        cycle_response = await client.post(
            "/api/controller/cycle",
            json={"bundle_artifact_id": bundle.envelope.artifact_id, "workspace_id": workspace_id, "dry_run": True},
        )
        cycle_data = cycle_response.json()
        assert cycle_data["success"] is True
        run_id = cycle_data["run_id"]
        assert cycle_data["workspace_id"] == workspace_id

        reports = (await client.get("/api/controller/reports", params=params)).json()
        assert run_id in {entry["run_id"] for entry in reports}

        detail_report = (await client.get(f"/api/controller/reports/{run_id}", params=params)).json()
        assert detail_report["bundle_artifact_id"] == bundle.envelope.artifact_id
