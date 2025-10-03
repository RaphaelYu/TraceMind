from __future__ import annotations

from tm.runtime.task import TaskEnvelope


def test_task_envelope_roundtrip():
    envelope = TaskEnvelope.new(flow_id="demo", input={"value": 1}, headers={"idempotency_key": "abc"})
    payload = envelope.to_dict()
    restored = TaskEnvelope.from_dict(payload)
    assert restored.task_id == envelope.task_id
    assert restored.flow_id == "demo"
    assert restored.input == {"value": 1}
    assert restored.idempotency_key == "abc"
    assert restored.to_dict()["attempt"] == 0


def test_envelope_composite_key_without_idempotency():
    envelope = TaskEnvelope.new(flow_id="demo", input={})
    assert envelope.composite_key == envelope.task_id
