import yaml

from tm.artifacts import ArtifactStatus, body_hash, load_yaml_artifact, verify


def _write_artifact(tmp_path, artifact_data):
    path = tmp_path / "artifact.yaml"
    path.write_text(yaml.safe_dump(artifact_data), encoding="utf-8")
    return path


def _base_plan_artifact(**overrides):
    artifact = {
        "envelope": {
            "artifact_id": "tm-plan-0001",
            "status": "candidate",
            "artifact_type": "plan",
            "version": "v0",
            "created_by": "tester",
            "created_at": "2024-01-01T00:00:00Z",
            "body_hash": "",
            "envelope_hash": "",
            "meta": {},
        },
        "body": {
            "plan_id": "plan-abc",
            "owner": "team",
            "summary": "execute steps",
            "steps": [
                {"name": "step-one", "reads": ["input"], "writes": ["output"]},
                {"name": "step-two", "reads": ["output"], "writes": ["final"]},
            ],
            "rules": [
                {"name": "rule-1", "triggers": ["input"], "steps": ["step-one"]},
                {"name": "rule-2", "triggers": ["output"], "steps": ["step-two"]},
            ],
        },
    }
    artifact.update(**overrides)
    return artifact


def _base_agent_bundle_artifact(**overrides):
    artifact = {
        "envelope": {
            "artifact_id": "tm-agent-bundle-0001",
            "status": "candidate",
            "artifact_type": "agent_bundle",
            "version": "v0",
            "created_by": "tester",
            "created_at": "2024-01-01T00:00:00Z",
            "body_hash": "",
            "envelope_hash": "",
            "meta": {},
        },
        "body": {
            "bundle_id": "tm-bundle/simple",
            "agents": [
                {
                    "agent_id": "tm-agent/runner:0.1",
                    "name": "runner",
                    "version": "0.1",
                    "runtime": {"kind": "tm-shell", "config": {"image": "runner:v0"}},
                    "contract": {
                        "inputs": [
                            {
                                "ref": "artifact:config",
                                "kind": "artifact",
                                "schema": "schemas/config-schema.json",
                                "required": True,
                                "mode": "read",
                            }
                        ],
                        "outputs": [
                            {
                                "ref": "state:workload",
                                "kind": "resource",
                                "schema": {"type": "object"},
                                "required": False,
                                "mode": "write",
                            }
                        ],
                        "effects": [
                            {
                                "name": "configure",
                                "kind": "resource",
                                "target": "state:workload",
                                "idempotency": {"type": "keyed", "key_fields": ["artifact_id"]},
                                "evidence": {"type": "hash", "path": "/state/config.hash"},
                            }
                        ],
                    },
                    "config_schema": {"type": "object"},
                    "evidence_outputs": [{"name": "config_hash", "description": "hash of the config"}],
                    "role": "initializer",
                }
            ],
            "plan": [
                {
                    "step": "init",
                    "agent_id": "tm-agent/runner:0.1",
                    "phase": "init",
                    "inputs": ["artifact:config"],
                    "outputs": ["state:workload"],
                }
            ],
            "meta": {"preconditions": ["artifact:config"]},
        },
    }
    artifact.update(**overrides)
    return artifact


def test_verify_accepts_well_formed_plan(tmp_path):
    artifact_data = _base_plan_artifact()
    path = _write_artifact(tmp_path, artifact_data)
    artifact = load_yaml_artifact(path)

    accepted, report = verify(artifact)

    assert accepted is artifact
    assert accepted.envelope.status == ArtifactStatus.ACCEPTED
    expected = body_hash(artifact.body_raw)
    assert accepted.envelope.body_hash == expected
    assert accepted.envelope.meta["hashes"]["body_hash"] == expected
    assert accepted.envelope.meta["determinism"] is True
    assert accepted.envelope.meta["produced_by"].startswith("tracemind.verifier.")
    assert report.success
    assert report.details["body_hash"] == expected


def test_verify_rejects_missing_reads(tmp_path):
    artifact_data = _base_plan_artifact()
    artifact_data["body"]["steps"][0].pop("reads", None)
    path = _write_artifact(tmp_path, artifact_data)
    artifact = load_yaml_artifact(path)

    accepted, report = verify(artifact)

    assert accepted is None
    assert not report.success
    assert any("reads" in err for err in report.errors)


def test_verify_accepts_well_formed_agent_bundle(tmp_path):
    artifact_data = _base_agent_bundle_artifact()
    path = _write_artifact(tmp_path, artifact_data)
    artifact = load_yaml_artifact(path)

    accepted, report = verify(artifact)

    assert accepted is artifact
    assert accepted.envelope.status == ArtifactStatus.ACCEPTED
    expected = body_hash(artifact.body_raw)
    assert accepted.envelope.body_hash == expected
    assert accepted.envelope.meta["hashes"]["body_hash"] == expected
    assert report.success
    assert report.details["body_hash"] == expected


def test_verify_rejects_unknown_agent_in_plan(tmp_path):
    artifact_data = _base_agent_bundle_artifact()
    artifact_data["body"]["plan"][0]["agent_id"] = "tm-agent/ghost:0.1"
    path = _write_artifact(tmp_path, artifact_data)
    artifact = load_yaml_artifact(path)

    accepted, report = verify(artifact)

    assert accepted is None
    assert not report.success
    assert any("not registered" in err for err in report.errors)


def test_verify_rejects_agent_bundle_missing_effect(tmp_path):
    artifact_data = _base_agent_bundle_artifact()
    artifact_data["body"]["agents"][0]["contract"]["effects"].clear()
    path = _write_artifact(tmp_path, artifact_data)
    artifact = load_yaml_artifact(path)

    accepted, report = verify(artifact)

    assert accepted is None
    assert not report.success
    assert any("EFFECT_REQUIRED" in err for err in report.errors)


def test_verify_rejects_plan_with_io_contract(tmp_path):
    artifact_data = _base_plan_artifact()
    artifact_data["body"]["io_contract"] = {
        "inputs": [
            {
                "ref": "artifact:config",
                "kind": "artifact",
                "schema": {"type": "object"},
                "required": True,
                "mode": "read",
            }
        ],
        "outputs": [
            {
                "ref": "state:record",
                "kind": "resource",
                "schema": {"type": "object"},
                "required": False,
                "mode": "write",
            }
        ],
        "effects": [
            {
                "name": "write-record",
                "kind": "resource",
                "target": "state:missing",
                "idempotency": {"type": "keyed", "key_fields": ["artifact_id"]},
                "evidence": {"type": "hash", "path": "/state/record.hash"},
            }
        ],
    }
    path = _write_artifact(tmp_path, artifact_data)
    artifact = load_yaml_artifact(path)

    accepted, report = verify(artifact)

    assert accepted is None
    assert not report.success
    assert any("EFFECT_TARGET" in err for err in report.errors)
