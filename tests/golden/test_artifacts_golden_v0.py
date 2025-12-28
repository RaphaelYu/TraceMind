from pathlib import Path
import pytest

from tm.artifacts import ArtifactStatus, load_yaml_artifact, verify

EXAMPLES = {
    "intent_TM-INT-0001.yaml": "1408997906dc867278382040313d1dbc5f17ecc38529009cc593da1a3dcf63fc",
    "plan_TM-INT-0001.yaml": "eab37e5073b949773a72b8418d7fdd83a3861f390243951a575371fe29d83d9c",
    "capabilities_example.yaml": "f96505e829a9543c2fab5b366e35b06c9ea3209ed3e308eda26f96925e66c568",
    "gap_map_example.yaml": "62ee22904e949116db7d23aaccdc6cb5caf727f2df614f9c880686a7efc1cb03",
    "backlog_example.yaml": "c655221f0842908fdf8d4e8c6dc27243f4b1c8d12f5a5a70ea07dd37332af209",
}


@pytest.mark.parametrize("filename,expected", EXAMPLES.items())
def test_example_artifacts_stable_hash(filename: str, expected: str):
    path = Path("specs/examples/artifacts_v0") / filename
    artifact = load_yaml_artifact(path)
    accepted, report = verify(artifact)
    assert accepted is not None
    assert report.success
    assert accepted.envelope.status == ArtifactStatus.ACCEPTED
    assert accepted.envelope.body_hash == expected
    assert report.details["body_hash"] == expected
    assert accepted.envelope.meta["hashes"]["body_hash"] == expected
