from __future__ import annotations

from typing import Any, Mapping

from tm.agents.runtime import RuntimeAgent


class NoopAgent(RuntimeAgent):
    AGENT_ID = "tm-agent/noop:0.1"

    def run(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        outputs: dict[str, Any] = {}
        fallback = next(iter(inputs.values()), None) if inputs else None
        for io_ref in self.contract.outputs:
            value = inputs.get(io_ref.ref, fallback)
            outputs[io_ref.ref] = value
        self.add_evidence("builtin.noop", {"outputs": outputs})
        return outputs
