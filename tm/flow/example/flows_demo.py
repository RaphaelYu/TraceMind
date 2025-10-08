from __future__ import annotations
from ..graph import FlowGraph, chain
from ..repo import FlowBase, flowrepo


class DemoSwitchParallel(FlowBase):
    name = "demo_switch_parallel"

    def build(self, **params) -> FlowGraph:
        f = FlowGraph(self.name)
        v = f.task("validate", uses="core.validate_payload", before=["chk.require_payload"])
        s = f.switch("route", key_from="$.vars.validate.ok", default="_DEFAULT")
        p = f.parallel(
            "fanout",
            uses=["parallel.add_one", "parallel.square"],
            max_workers=4,
            timeout_ms=800,
        )
        a = f.task("annotate", uses="adapters.echo.annotate", after=["chk.emit_metric"])
        d = f.finish("done")

        chain(f, v, s)
        f.link_case(s, p, case=True)
        f.link_case(s, a, case=False)
        f.link_case(s, a, case="_DEFAULT")
        chain(f, p, a, d)
        f.set_entry(v)
        return f


flowrepo.register(DemoSwitchParallel)


def build_demo_flow() -> FlowGraph:
    return DemoSwitchParallel().build()
