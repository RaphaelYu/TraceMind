from tm.service import BindingRule, BindingSpec, Operation
from tm.service.router import OperationRouter


class DummyRuntime:
    def __init__(self):
        self.calls = []

    def run(self, name, inputs=None, response_mode=None):  # noqa: ANN001
        self.calls.append((name, inputs, response_mode))
        return {"status": "immediate", "result": {"ok": True}}


class RecordingHook:
    def __init__(self):
        self.before_ctx = None
        self.after_result = None

    def before_route(self, ctx):  # noqa: ANN001
        ctx["selected"] = "special"
        self.before_ctx = dict(ctx)

    def after_result(self, result):  # noqa: ANN001
        self.after_result = dict(result)


def test_decision_hook_can_override_binding():
    binding = BindingSpec(
        model="Generic",
        rules=[
            BindingRule(operation=Operation.READ, flow_name="flow-default"),
            BindingRule(
                operation=Operation.READ,
                flow_name="flow-special",
                predicate=lambda ctx: ctx.get("selected") == "special",
            ),
        ],
    )

    runtime = DummyRuntime()
    hook = RecordingHook()
    router = OperationRouter(runtime, {"Generic": binding}, hook=hook)

    payload = {"data": {"id": "123"}}
    result = router.dispatch(model="Generic", operation=Operation.READ, payload=payload, context={})

    assert runtime.calls[0][0] == "flow-special"
    assert hook.before_ctx["selected"] == "special"
    assert result["flow"] == "flow-special"
    assert hook.after_result["flow"] == "flow-special"
