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
