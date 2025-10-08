from __future__ import annotations

from tm.validate.static import find_conflicts


def test_detects_arm_overlap():
    policies = [
        {
            "policy_id": "p1",
            "arms": [
                {"name": "a", "if": {"cost": "<=0.5"}},
                {"name": "b", "if": {"cost": "<0.6"}},
            ],
        }
    ]
    conflicts = find_conflicts([], policies)
    assert any(conflict.kind == "policy.arm_overlap" for conflict in conflicts)


def test_policy_id_collision():
    conflicts = find_conflicts([], [{"policy_id": "dup"}, {"policy_id": "dup"}])
    kinds = {conflict.kind for conflict in conflicts}
    assert "policy.id_collision" in kinds


def test_missing_policy_id():
    conflicts = find_conflicts([], [{}, {"policy_id": "valid"}])
    kinds = {conflict.kind for conflict in conflicts}
    assert "policy.missing_id" in kinds


def test_flow_id_collision_and_missing():
    flows = [{"id": "flow1"}, {"id": "flow1"}, {}]
    kinds = {conflict.kind for conflict in find_conflicts(flows, [])}
    assert "flow.id_collision" in kinds
    assert "flow.missing_id" in kinds


def test_lock_conflict_detected():
    flows = [
        {
            "id": "flow_a",
            "steps": {
                "s1": {"locks": [{"name": "db", "mode": "exclusive"}]},
            },
        },
        {
            "id": "flow_b",
            "steps": {
                "t1": {"locks": [{"name": "db", "mode": "shared"}]},
            },
        },
    ]
    conflicts = find_conflicts(flows, [])
    assert any(conflict.kind == "flow.lock_conflict" for conflict in conflicts)


def test_cron_overlap_detected():
    flows = [
        {"id": "flow_a", "schedule": {"cron": "0 * * * *"}},
        {"id": "flow_b", "schedule": {"cron": "0 * * * *"}},
    ]
    conflicts = find_conflicts(flows, [])
    assert any(conflict.kind == "flow.cron_overlap" for conflict in conflicts)
