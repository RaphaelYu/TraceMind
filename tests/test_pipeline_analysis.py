from tm.pipeline.analysis import analyze_plan
from tm.pipeline.engine import Plan, Rule, StepSpec


def _noop(ctx):
    return ctx


def _make_plan() -> Plan:
    steps = {
        "w_status": StepSpec("w_status", [], ["status"], _noop),
        "r_status": StepSpec("r_status", ["status"], [], _noop),
        "dead": StepSpec("dead", ["x"], ["x"], _noop),
        "w_status_again": StepSpec("w_status_again", ["status"], ["status.value"], _noop),
    }
    rules = [
        Rule("rule_a", ["status"], ["w_status", "r_status"]),
        Rule("rule_b", ["status.detail"], ["w_status_again"]),
        Rule("empty_steps", ["meta.note"], []),
        Rule("empty_triggers", [], ["w_status"]),
    ]
    return Plan(steps=steps, rules=rules)


def test_analyze_plan_reports_conflicts_and_coverage():
    report = analyze_plan(_make_plan(), focus_fields=["status", "services[].state", "unknown"])

    deps = report.graphs.step_deps
    assert set(deps["w_status"]) == {"r_status", "w_status_again"}
    assert "r_status" in deps["w_status_again"]
    assert report.graphs.topo  # DAG ordering present when no cycles

    coverage = report.coverage
    assert coverage.unused_steps == ["dead"]
    assert coverage.empty_rules == ["empty_steps"]
    assert coverage.empty_triggers == ["empty_triggers"]
    assert set(coverage.focus_uncovered) == {"services[].state", "unknown"}

    kinds = {(c.kind, c.where) for c in report.conflicts}
    assert ("suspicious-rule", "empty_steps") in kinds
    assert any(k == "write-write" and where == "cross-rule" for k, where in kinds)

    assert "R:rule_a" in report.dot_rules_steps
    assert "w_status" in report.dot_step_deps


def test_analyze_plan_detects_cycles():
    steps = {
        "a": StepSpec("a", ["foo"], ["bar"], _noop),
        "b": StepSpec("b", ["bar"], ["foo"], _noop),
    }
    rules = [Rule("cycle", ["foo"], ["a", "b"])]
    plan = Plan(steps=steps, rules=rules)

    report = analyze_plan(plan)

    assert report.graphs.topo == []
    assert any(set(cycle) == {"a", "b"} or cycle[:-1] == ["a", "b"] for cycle in report.graphs.cycles)
