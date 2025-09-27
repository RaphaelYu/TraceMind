from __future__ import annotations

import json

import pytest

from tm.run_recipe import run_recipe
from tests.test_recipe_loader import LINEAR_RECIPE, SWITCH_RECIPE, PARALLEL_RECIPE


@pytest.mark.parametrize(
    "recipe",
    [LINEAR_RECIPE, SWITCH_RECIPE, PARALLEL_RECIPE],
)
def test_run_recipe_success(recipe):
    payload = {"payload": {"document": "sample", "route": "auto"}}
    result = run_recipe(json.dumps(recipe), payload)
    assert result["status"] in {"ok", "error"}
    assert "run_id" in result
    assert "exec_ms" in result


def test_run_recipe_handles_error():
    bad = json.dumps({"flow": {"id": "bad", "version": "1", "entry": "missing", "steps": [], "edges": []}})
    result = run_recipe(bad)
    assert result["status"] == "error"
    assert "error" in result["output"]
