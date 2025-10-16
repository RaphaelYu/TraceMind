from __future__ import annotations

import json
from pathlib import Path

import pytest

from tm.dsl import EvaluationInput, evaluate_policy, parse_pdl_document
from tm.dsl.compiler_policy import compile_policy
from tm.dsl.evaluator import load_policy, PolicyEvaluationError

PDL_SAMPLE = """
version: pdl/v0
arms:
  default:
    threshold: 75.0
    action_on_violation: WRITE_BACK
epsilon: 0.1
evaluate:
  temp := coalesce(values[\"temp\"], first_numeric(values))
  if temp >= arms.active.threshold:
    choose:
      exploit: action = arms.active.action_on_violation
      explore: random([\"NONE\",\"WRITE_BACK\",\"SHUTDOWN\"]) with p=epsilon
  else:
    action = \"NONE\"
emit:
  action: action
"""


@pytest.fixture()
def compiled_policy(tmp_path: Path):
    path = tmp_path / "policy.pdl"
    path.write_text(PDL_SAMPLE, encoding="utf-8")
    policy_ir = parse_pdl_document(path.read_text(encoding="utf-8"), filename=str(path))
    compilation = compile_policy(policy_ir, source=path, policy_id="test-policy")
    json_path = tmp_path / "policy.json"
    json_path.write_text(json.dumps(compilation.data, indent=2), encoding="utf-8")
    return compilation.data


def test_policy_evaluator_below_threshold(compiled_policy: dict[str, object]):
    result = evaluate_policy(
        compiled_policy,
        EvaluationInput(values={"temp": 60.0}, epsilon=0.1, random_func=lambda: 0.5),
    )
    assert result["action"] == "NONE"


def test_policy_evaluator_above_threshold_exploit(compiled_policy: dict[str, object]):
    result = evaluate_policy(
        compiled_policy,
        EvaluationInput(values={"temp": 80.0}, epsilon=0.1, random_func=lambda: 0.5),
    )
    assert result["action"] == "WRITE_BACK"


def test_policy_evaluator_above_threshold_explore(compiled_policy: dict[str, object]):
    calls = [0]

    def deterministic_random() -> float:
        calls[0] += 1
        return 0.05 if calls[0] == 1 else 0.6

    result = evaluate_policy(
        compiled_policy,
        EvaluationInput(values={"temp": 90.0}, epsilon=0.2, random_func=deterministic_random),
    )
    assert result["action"] in {"NONE", "WRITE_BACK", "SHUTDOWN"}


def test_load_policy_error(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("not json", encoding="utf-8")
    with pytest.raises(PolicyEvaluationError):
        load_policy(bad_path)
