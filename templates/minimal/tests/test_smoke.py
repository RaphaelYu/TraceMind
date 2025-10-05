from __future__ import annotations

from pathlib import Path

from tm.run_recipe import run_recipe


def test_hello_flow(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    recipe_path = project_root / "flows" / "hello.yaml"
    result = run_recipe(recipe_path, {"name": "world"})
    assert result["status"] == "ok"
    assert result["output"]["message"] == "Hello, world!"
