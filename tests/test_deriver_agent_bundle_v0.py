from __future__ import annotations

from pathlib import Path

import yaml

from tm.artifacts import Artifact
from tm.artifacts.report import ArtifactVerificationReport
from tm.derive.tm_agent_bundle import derive_from_intent


def _intent_artifact_path() -> Path:
    return Path("specs/examples/artifacts_v0/intent_TM-INT-0001.yaml")


def test_codex_deriver_creates_accepted_bundle(tmp_path: Path) -> None:
    success = derive_from_intent(_intent_artifact_path(), tmp_path)
    assert success
    accepted_bundle = tmp_path / "agent_bundle_accepted.yaml"
    assert accepted_bundle.exists()
    artifact = yaml.safe_load(accepted_bundle.read_text(encoding="utf-8"))
    assert artifact["envelope"]["status"] == "accepted"
    assert artifact["envelope"]["meta"].get("determinism") is True
    gap_map = yaml.safe_load((tmp_path / "gap_map.yaml").read_text(encoding="utf-8"))
    assert gap_map["body"]["severity"] == "low"
    backlog = yaml.safe_load((tmp_path / "backlog.yaml").read_text(encoding="utf-8"))
    assert backlog["body"]["items"][0]["priority"] == "low"


def test_codex_deriver_records_gaps_when_verify_fails(tmp_path: Path) -> None:
    def _fake_verify(_: Artifact):
        report = ArtifactVerificationReport("fake")
        report.add_error("EFFECT_TARGET: missing http response")
        return None, report

    success = derive_from_intent(_intent_artifact_path(), tmp_path, verify_fn=_fake_verify)
    assert not success
    assert not (tmp_path / "agent_bundle_accepted.yaml").exists()
    gap_map = yaml.safe_load((tmp_path / "gap_map.yaml").read_text(encoding="utf-8"))
    assert "EFFECT_TARGET" in gap_map["body"]["gap_description"]
    backlog = yaml.safe_load((tmp_path / "backlog.yaml").read_text(encoding="utf-8"))
    assert "EFFECT_TARGET" in backlog["body"]["items"][0]["description"]
