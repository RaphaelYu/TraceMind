from __future__ import annotations

from typing import Mapping

from tm.agents.runtime import RuntimeAgent


class HttpMockAgent(RuntimeAgent):
    AGENT_ID = "tm-agent/http-mock:0.1"

    def run(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        request = self._resolve_request(inputs)
        response = self._match_response(request)
        self.add_evidence(
            "builtin.http_mock",
            {
                "request": request,
                "response": response,
            },
        )
        outputs: dict[str, object] = {}
        for io_ref in self.contract.outputs:
            outputs[io_ref.ref] = response
        return outputs

    def _resolve_request(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        payload = inputs.get("artifact:http_request")
        if payload is None:
            raise RuntimeError("http_mock agent requires 'artifact:http_request' input")
        if not isinstance(payload, Mapping):
            raise RuntimeError("http_mock request payload must be a mapping")
        return payload

    def _match_response(self, request: Mapping[str, object]) -> dict[str, object]:
        method = str(request.get("method", "GET")).upper()
        url = str(request.get("url", ""))
        key = f"{method} {url}"
        config_responses = self.config.get("responses", {})
        if not isinstance(config_responses, Mapping):
            config_responses = {}
        candidate = config_responses.get(key) or config_responses.get(url) or config_responses.get(method)
        default_response = self.config.get("default_response")
        if candidate is None:
            candidate = default_response
        if candidate is None:
            candidate = {}
        if not isinstance(candidate, Mapping):
            candidate = {}
        return {
            "status": int(candidate.get("status", 200)),
            "headers": dict(candidate.get("headers") or {}),
            "body": candidate.get("body", ""),
        }
