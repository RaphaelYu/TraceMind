from tm.helpers import plan_has_patch, apply_patch


def test_plan_has_patch_detects_patch():
    ctx = {"reflect": {"reflection": {"plan_patch": {"ops": ["x"]}}}}
    assert plan_has_patch(ctx, {}) is True
    assert plan_has_patch({}, {"plan_patch": {"ops": ["x"]}}) is True
    assert not plan_has_patch({}, {})


def test_apply_patch_updates_document():
    doc = {
        "steps": [
            {"inputs": {"value": 1}},
            {"inputs": {"value": 2}},
        ]
    }
    patch = {"ops": [{"op": "replace", "path": "/steps/1/inputs/value", "value": 42}]}
    updated = apply_patch(doc, patch)
    assert updated["steps"][1]["inputs"]["value"] == 42
    assert doc["steps"][1]["inputs"]["value"] == 2
