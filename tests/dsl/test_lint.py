from __future__ import annotations

from pathlib import Path
import textwrap

from tm.dsl.lint import lint_path


def _lint_snippet(tmp_path: Path, text: str) -> list[str]:
    path = tmp_path / "sample.wdl"
    path.write_text(textwrap.dedent(text).strip(), encoding="utf-8")
    return [issue.code for issue in lint_path(path)]


def test_unknown_step_reference(tmp_path: Path) -> None:
    text = """
    version: dsl/v0
    workflow: example
    steps:
      - first(op.echo):
          value: 1
      - second(op.echo):
          copy: $step.missing.value
    outputs:
      result: $step.second
    """
    issues = _lint_snippet(tmp_path, text)
    assert "unknown-step-ref" in issues


def test_branch_step_not_available_outside(tmp_path: Path) -> None:
    text = """
    version: dsl/v0
    workflow: branch
    inputs:
      flag: string
    steps:
      - when $input.flag in ["YES"]:
          branch(op.write):
            value: 1
      - after(op.echo):
          value: $step.branch.value
    outputs:
      result: $step.after
    """
    issues = _lint_snippet(tmp_path, text)
    assert "unknown-step-ref" in issues


def test_missing_input_detected(tmp_path: Path) -> None:
    text = """
    version: dsl/v0
    workflow: missing-input
    inputs:
      defined: string
    steps:
      - first(op.echo):
          value: $input.undefined
    outputs:
      result: $step.first
    """
    issues = _lint_snippet(tmp_path, text)
    assert "missing-input" in issues
