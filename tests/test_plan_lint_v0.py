from tm.lint.plan_lint import lint_plan


def test_step_missing_reads_writes():
    plan = {
        "steps": [
            {"name": "step-missing-reads", "writes": ["out"]},
            {"name": "step-missing-writes", "reads": ["in"]},
        ],
        "rules": [],
    }
    issues = lint_plan(plan)
    assert any(issue.code == "STEP_IO" and "reads" in issue.message for issue in issues)
    assert any(issue.code == "STEP_IO" and "writes" in issue.message for issue in issues)


def test_rule_references_unknown_step():
    plan = {
        "steps": [{"name": "step-one", "reads": ["in"], "writes": ["out"]}],
        "rules": [{"name": "rule-one", "triggers": ["in"], "steps": ["missing-step"]}],
    }
    issues = lint_plan(plan)
    assert any(issue.code == "RULE_REF" for issue in issues)
