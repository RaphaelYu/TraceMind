import pytest

from tm.flow.graph import FlowGraph, NodeKind, chain


def test_task_sets_entry_and_persists_step_data():
    flow = FlowGraph("demo")

    node_id = flow.task("task1", uses="pkg", retries=2)

    assert flow.entry() == node_id
    step = flow.node(node_id)
    assert step.id == node_id
    assert step.kind is NodeKind.TASK
    assert step.uses == "pkg"
    assert step.cfg == {"retries": 2}


def test_duplicate_node_id_raises_value_error():
    flow = FlowGraph("dup")
    flow.finish("end")

    with pytest.raises(ValueError):
        flow.task("end", uses="pkg")


def test_set_entry_requires_existing_node():
    flow = FlowGraph("entry")

    with pytest.raises(KeyError):
        flow.set_entry("missing")


def test_entry_requires_prior_assignment():
    flow = FlowGraph("no-entry")

    with pytest.raises(RuntimeError):
        flow.entry()


def test_link_case_stores_case_attribute():
    flow = FlowGraph("edges")
    src = flow.task("switch", uses="pkg")
    dst = flow.finish("finish")

    flow.link_case(src, dst, case="foo")

    assert flow.successors(src) == [dst]
    assert flow.edge_attr(src, dst, "case") == "foo"


def test_parallel_cfg_normalization():
    flow = FlowGraph("parallel")

    node_id = flow.parallel("p", uses=("a", "b"), max_workers="8", extra=True)

    step = flow.node(node_id)
    assert step.kind is NodeKind.PARALLEL
    assert step.cfg == {"uses": ["a", "b"], "max_workers": 8, "extra": True}


def test_chain_links_all_nodes():
    flow = FlowGraph("chain")
    a = flow.task("a", uses="pkg")
    b = flow.task("b", uses="pkg")
    c = flow.finish("c")

    last = chain(flow, a, b, c)

    assert last == c
    assert flow.successors(a) == [b]
    assert flow.successors(b) == [c]
