from typing import Mapping

import pytest

from tm.agents.models import (
    AgentContract,
    AgentEvidenceOutput,
    AgentRuntime,
    AgentSpec,
    EffectIdempotency,
    EffectRef,
    IORef,
)
from tm.agents.registry import AgentRegistryError, register_agent, resolve_agent, unregister_agent
from tm.agents.runtime import RuntimeAgent


class EchoAgent(RuntimeAgent):
    def run(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        return {"echo": inputs}


def _make_sample_spec(agent_id: str) -> AgentSpec:
    contract = AgentContract(
        inputs=[
            IORef(ref="artifact:config", kind="artifact", schema="schemas/config.json", required=True, mode="read")
        ],
        outputs=[IORef(ref="state:result", kind="resource", schema={"type": "object"}, required=False, mode="write")],
        effects=[
            EffectRef(
                name="write-result",
                kind="resource",
                target="state:result",
                idempotency=EffectIdempotency(type="keyed", key_fields=["artifact_id"]),
                rollback=None,
                evidence={"type": "hash", "path": "/state/result.hash"},
            )
        ],
    )
    runtime = AgentRuntime(kind="tm-shell", config={"image": "example"})
    return AgentSpec(
        agent_id=agent_id,
        name="echo",
        version="0.1",
        runtime=runtime,
        contract=contract,
        config_schema={"type": "object"},
        evidence_outputs=[AgentEvidenceOutput(name="result_hash")],
    )


def test_registry_resolves_registered_agent():
    spec = _make_sample_spec("tm-agent/echo:0.1")
    register_agent(spec.agent_id, lambda spec, config: EchoAgent(spec, config))
    agent = resolve_agent(spec.agent_id, spec, {"mode": "test"})
    agent.init({"context": "ok"})
    output = agent.run({"payload": "value"})
    assert output == {"echo": {"payload": "value"}}
    agent.finalize()
    unregister_agent(spec.agent_id)


def test_registry_raises_for_unknown_agent():
    spec = _make_sample_spec("tm-agent/missing:0.1")
    with pytest.raises(AgentRegistryError):
        resolve_agent(spec.agent_id, spec, {})
