from __future__ import annotations

import json

import pytest

from tm.flow.recipe_loader import RecipeLoader, RecipeError

HANDLERS = "tests.examples"

LINEAR_RECIPE = {
    "flow": {
        "id": "checkout-linear",
        "version": "1.0.0",
        "entry": "prepare",
        "steps": [
            {
                "id": "prepare",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.prepare"},
            },
            {
                "id": "charge",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.charge"},
            },
            {"id": "done", "kind": "finish"},
        ],
        "edges": [
            {"from": "prepare", "to": "charge"},
            {"from": "charge", "to": "done"},
        ],
    }
}

SWITCH_RECIPE = {
    "flow": {
        "id": "fraud-review",
        "version": "2024.05.01",
        "entry": "score",
        "steps": [
            {
                "id": "score",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.prepare"},
            },
            {
                "id": "router",
                "kind": "switch",
                "config": {"cases": {"manual": "manual", "auto": "approve"}, "default": "auto"},
                "hooks": {"run": f"{HANDLERS}.risk_route"},
            },
            {
                "id": "manual",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.manual_review"},
            },
            {
                "id": "approve",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.auto_approve"},
            },
            {"id": "complete", "kind": "finish"},
        ],
        "edges": [
            {"from": "score", "to": "router"},
            {"from": "router", "to": "manual", "when": "manual"},
            {"from": "router", "to": "approve", "when": "auto"},
            {"from": "manual", "to": "complete"},
            {"from": "approve", "to": "complete"},
        ],
    }
}

PARALLEL_RECIPE = {
    "flow": {
        "id": "document-process",
        "version": "1.2.3",
        "entry": "ingest",
        "steps": [
            {
                "id": "ingest",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.ingest"},
            },
            {
                "id": "fanout",
                "kind": "parallel",
                "config": {"branches": ["extract_text", "classify"], "mode": "all"},
                "hooks": {"run": f"{HANDLERS}.run_parallel"},
            },
            {
                "id": "extract_text",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.extract_text"},
            },
            {
                "id": "classify",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.classify"},
            },
            {
                "id": "patch",
                "kind": "task",
                "hooks": {"run": f"{HANDLERS}.patch_payload"},
            },
            {"id": "finish", "kind": "finish"},
        ],
        "edges": [
            {"from": "ingest", "to": "fanout"},
            {"from": "fanout", "to": "extract_text"},
            {"from": "fanout", "to": "classify"},
            {"from": "extract_text", "to": "patch"},
            {"from": "classify", "to": "patch"},
            {"from": "patch", "to": "finish"},
        ],
    }
}


@pytest.mark.parametrize(
    "recipe",
    [LINEAR_RECIPE, SWITCH_RECIPE, PARALLEL_RECIPE],
)
def test_recipe_loader_builds_flow_spec(recipe):
    loader = RecipeLoader()
    spec = loader.load(json.dumps(recipe))
    assert spec.flow_id == recipe["flow"]["id"]
    assert spec.entrypoint == recipe["flow"]["entry"]
    for step in recipe["flow"]["steps"]:
        step_def = spec.step(step["id"])  # type: ignore[arg-type]
        assert step_def.name == step["id"]
    # Flow revision stable and non-empty
    rev = spec.flow_revision()
    assert rev.startswith("rev-")


def test_yaml_recipe(tmp_path):
    pytest.importorskip("yaml")
    loader = RecipeLoader()
    yaml_text = """
flow:
  id: yaml-demo
  version: "0.1.0"
  entry: prepare
  steps:
    - id: prepare
      kind: task
      hooks:
        run: tests.examples.prepare
    - id: finish
      kind: finish
  edges:
    - {from: prepare, to: finish}
"""
    spec = loader.load(yaml_text)
    assert spec.flow_id == "yaml-demo"


def test_cycle_detection():
    loader = RecipeLoader()
    bad = {
        "flow": {
            "id": "cycle",
            "version": "1",
            "entry": "a",
            "steps": [
                {"id": "a", "kind": "task", "hooks": {"run": f"{HANDLERS}.prepare"}},
                {"id": "b", "kind": "task", "hooks": {"run": f"{HANDLERS}.prepare"}},
            ],
            "edges": [
                {"from": "a", "to": "b"},
                {"from": "b", "to": "a"},
            ],
        }
    }
    with pytest.raises(RecipeError):
        loader.load(json.dumps(bad))


def test_unknown_step_reference():
    loader = RecipeLoader()
    bad = {
        "flow": {
            "id": "dangling",
            "version": "1",
            "entry": "a",
            "steps": [
                {"id": "a", "kind": "task", "hooks": {"run": f"{HANDLERS}.prepare"}},
                {"id": "finish", "kind": "finish"},
            ],
            "edges": [
                {"from": "a", "to": "missing"},
            ],
        }
    }
    with pytest.raises(RecipeError):
        loader.load(json.dumps(bad))
