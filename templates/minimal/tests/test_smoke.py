from __future__ import annotations

from pathlib import Path

from tm.run_recipe import run_recipe


def test_hello_flow(tmp_path, monkeypatch):
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(project_root))
    recipe_path = project_root / "flows" / "hello.yaml"
    result = run_recipe(recipe_path, {"name": "world"})
    assert result["status"] == "ok"
    state = result["output"].get("state", {}) if isinstance(result.get("output"), dict) else {}
    assert state.get("message") == "Hello, world!"
