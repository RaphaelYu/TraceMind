from pathlib import Path

from tm.pipeline.engine import Plan, Rule, StepSpec
from tm.verify.adapter import TraceMindAdapter
from tm.verify.explorer import Explorer
from tm.verify.report import build_report
from tm.verify.spec import PropertySpec, VerifySpec, load_plan


def _dummy_fn(ctx):
    return ctx


def test_invariant_failure_missing_read(tmp_path):
    plan = load_plan(Path("tests/fixtures/verify/plan.json"))
    spec = VerifySpec(
        initial_store={},
        initial_pending=[],
        changed_paths=["start"],
        invariants=["Pending(read_profile) AND Has(user)"],
        properties=[],
    )
    adapter = TraceMindAdapter.from_plan(
        plan,
        initial_store=spec.initial_store,
        changed_paths=spec.changed_paths,
        initial_pending=spec.initial_pending,
    )
    model = Explorer(adapter).run(max_depth=3)
    report = build_report(invariants=spec.invariants, properties=spec.properties, model=model, adapter=adapter)
    assert report.invariants and not report.invariants[0].ok
    assert report.invariants[0].violated_at == 0
    assert report.invariants[0].path == [0]


def test_deadlock_detected_when_no_reads_available():
    steps = {
        "need_input": StepSpec(name="need_input", reads=["missing"], writes=[], fn=_dummy_fn),
    }
    rules = [Rule(name="on_start", triggers=["start"], steps=["need_input"])]
    plan = Plan(steps=steps, rules=rules)
    adapter = TraceMindAdapter.from_plan(plan, initial_store={}, changed_paths=["start"])
    model = Explorer(adapter).run(max_depth=1)
    assert model.deadlocks, "expected deadlock when no enabled steps"


def test_ctl_ef_success_af_failure():
    steps = {
        "goal": StepSpec(name="goal", reads=[], writes=["goal"], fn=_dummy_fn),
        "loop": StepSpec(name="loop", reads=[], writes=["loop"], fn=_dummy_fn),
    }
    rules = [
        Rule(name="start", triggers=["start"], steps=["goal", "loop"]),
        Rule(name="loop_rule", triggers=["loop"], steps=["loop"]),
    ]
    plan = Plan(steps=steps, rules=rules)
    spec = VerifySpec(
        initial_store={},
        initial_pending=[],
        changed_paths=["start", "loop"],
        invariants=[],
        properties=[
            PropertySpec(name="reach_goal", formula="EF Done(goal)"),
            PropertySpec(name="all_paths_goal", formula="AF Done(goal)"),
        ],
    )
    adapter = TraceMindAdapter.from_plan(plan, initial_store=spec.initial_store, changed_paths=spec.changed_paths)
    model = Explorer(adapter).run(max_depth=6)
    report = build_report(invariants=spec.invariants, properties=spec.properties, model=model, adapter=adapter)
    reach = next(p for p in report.properties if p.name == "reach_goal")
    assert reach.ok
    af = next(p for p in report.properties if p.name == "all_paths_goal")
    assert not af.ok
    assert af.counterexample, "AF failure should include a counterexample path"
