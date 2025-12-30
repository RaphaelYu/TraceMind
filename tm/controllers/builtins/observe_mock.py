from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from tm.agents.runtime import RuntimeAgent
from tm.artifacts.normalize import normalize_body


class ObserveMockAgent(RuntimeAgent):
    AGENT_ID = "tm-agent/controller-observe:0.1"

    def run(self, inputs: Mapping[str, Any]) -> Mapping[str, object]:
        environment = self._prepare_environment()
        constraints = self._prepare_constraints()
        timestamp = self.config.get("timestamp", "2025-01-01T00:00:00Z")
        snapshot_id = self.config.get("snapshot_id") or self._default_snapshot_id(environment)
        data_hash = self._hash_environment(environment, constraints)
        snapshot = {
            "snapshot_id": snapshot_id,
            "timestamp": timestamp,
            "environment": environment,
            "constraints": constraints,
            "data_hash": data_hash,
        }
        self.add_evidence("builtin.observer.snapshot", snapshot)
        return {"state:env.snapshot": snapshot}

    def _prepare_environment(self) -> dict[str, object]:
        raw = self.config.get("environment")
        environment: dict[str, object]
        if isinstance(raw, Mapping):
            environment = dict(raw)
        else:
            environment = {}
        if not environment:
            environment = {"state": {"phase": "mock"}}
        return environment

    def _prepare_constraints(self) -> list[Mapping[str, object]]:
        raw = self.config.get("constraints")
        if raw is None:
            return [{"type": "guard", "rule": "mock-observe", "description": "Mock observation constraints"}]
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            raise RuntimeError("constraints must be a sequence of mappings")
        constraints: list[Mapping[str, object]] = []
        for entry in raw:
            if not isinstance(entry, Mapping):
                raise RuntimeError("constraints entries must be mappings")
            constraints.append(dict(entry))
        return constraints

    @staticmethod
    def _hash_environment(environment: Mapping[str, object], constraints: Sequence[Mapping[str, object]]) -> str:
        payload = {"environment": dict(environment), "constraints": [dict(item) for item in constraints]}
        normalized = normalize_body(payload)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _default_snapshot_id(environment: Mapping[str, object]) -> str:
        state = environment.get("state")
        if isinstance(state, Mapping):
            phase = state.get("phase")
            if isinstance(phase, str) and phase:
                return f"env-{phase}"
        fallback = environment.get("phase")
        if isinstance(fallback, str) and fallback:
            return f"env-{fallback}"
        return "env-mock"
