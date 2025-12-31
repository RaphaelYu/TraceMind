from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Mapping

from tm.agents.models import AgentSpec
from tm.connectors.http_agent import HttpConnectorAgent


class RecordingHandler(BaseHTTPRequestHandler):
    capture: list[Mapping[str, object]] = []
    response_body = b'{"ok": true}'
    response_status = 200

    def do_GET(self) -> None:
        self._record()

    def do_POST(self) -> None:
        self._record()

    def do_PUT(self) -> None:
        self._record()

    def do_PATCH(self) -> None:
        self._record()

    def _record(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length) if length else b""
        RecordingHandler.capture.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": payload,
            }
        )
        self.send_response(self.response_status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(RecordingHandler.response_body)

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover - suppress logging
        pass


def _start_server(handler_cls: type[BaseHTTPRequestHandler]) -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("localhost", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _make_agent_spec() -> AgentSpec:
    data = {
        "agent_id": HttpConnectorAgent.AGENT_ID,
        "name": "controller-http",
        "version": "0.1",
        "runtime": {"kind": "python", "config": {}},
        "contract": {
            "inputs": [
                {
                    "ref": "state:env.snapshot",
                    "kind": "resource",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "read",
                },
                {
                    "ref": "artifact:proposed.plan",
                    "kind": "artifact",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "read",
                },
            ],
            "outputs": [
                {
                    "ref": "artifact:execution.report",
                    "kind": "artifact",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "write",
                },
                {
                    "ref": "state:act.result",
                    "kind": "resource",
                    "schema": {"type": "object"},
                    "required": True,
                    "mode": "write",
                },
            ],
            "effects": [
                {
                    "name": "execution_report",
                    "kind": "resource",
                    "target": "artifact:execution.report",
                    "idempotency": {"type": "keyed", "key_fields": ["plan_id"]},
                    "evidence": {"type": "hash", "path": "/execution_report"},
                }
            ],
        },
        "config_schema": {"type": "object"},
        "evidence_outputs": [{"name": "http", "description": "http connector"}],
    }
    return AgentSpec.from_mapping(data)


def _snapshot_payload() -> Mapping[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "timestamp": "2025-01-01T00:00:00Z",
        "environment": {"status": "ready"},
        "constraints": [],
        "data_hash": "hash-1",
    }


def _plan_payload(decisions: list[Mapping[str, object]]) -> Mapping[str, object]:
    return {
        "plan_id": "plan-123",
        "intent_id": "intent.controller.http",
        "decisions": decisions,
        "llm_metadata": {
            "model": "fake",
            "prompt_hash": "hash",
            "determinism_hint": "deterministic",
            "model_id": None,
            "model_version": None,
            "prompt_template_version": "1",
            "prompt_version": "1",
            "config_id": "cfg",
            "inputs_hash": "inputs",
        },
        "summary": "http effect",
        "policy_requirements": [],
    }


def _agent_config() -> Mapping[str, object]:
    return {
        "allowlist": [
            {
                "name": "example",
                "url_prefix": "http://localhost",
                "methods": ["GET", "POST", "PUT", "PATCH"],
            }
        ]
    }


def _request_decision(
    base_url: str, allowlist_key: str, method: str = "GET", body: object | None = None
) -> Mapping[str, object]:
    return {
        "effect_ref": "resource:http",
        "idempotency_key": "idem-123",
        "target_state": {
            "method": method,
            "url": base_url,
            "allowlist_key": allowlist_key,
            "headers": {"x-test": "value"},
            "params": {"q": "1"},
            "body": body,
            "idempotency_key": "idem-123",
        },
    }


def test_http_connector_successful_request() -> None:
    RecordingHandler.capture.clear()
    server, thread = _start_server(RecordingHandler)
    try:
        port = server.server_address[1]
        spec = _make_agent_spec()
        config = _agent_config()
        agent = HttpConnectorAgent(spec, config)
        decision = _request_decision(f"http://localhost:{port}/api", "example")
        output = agent.run(
            {
                "state:env.snapshot": _snapshot_payload(),
                "artifact:proposed.plan": _plan_payload([decision]),
            }
        )
        report = output["artifact:execution.report"]
        assert report["status"] == "succeeded"
        artifact_refs = report["artifact_refs"]
        assert "resource:http" in artifact_refs
        request_record = RecordingHandler.capture[0]
        assert request_record["method"] == "GET"
        assert "/api" in request_record["path"]
    finally:
        server.shutdown()
        thread.join(timeout=1)


def test_http_connector_enforces_allowlist() -> None:
    spec = _make_agent_spec()
    config = _agent_config()
    agent = HttpConnectorAgent(spec, config)
    decision = _request_decision("http://example.org/api", "missing")
    output = agent.run(
        {
            "state:env.snapshot": _snapshot_payload(),
            "artifact:proposed.plan": _plan_payload([decision]),
        }
    )
    report = output["artifact:execution.report"]
    assert report["status"] == "failed"
    policy_decisions = report["policy_decisions"]
    assert policy_decisions[0]["allowed"] is False
    assert "allowlist" in policy_decisions[0]["reason"]


def test_http_connector_sets_idempotency_header() -> None:
    RecordingHandler.capture.clear()
    server, thread = _start_server(RecordingHandler)
    try:
        port = server.server_address[1]
        spec = _make_agent_spec()
        config = _agent_config()
        agent = HttpConnectorAgent(spec, config)
        decision = _request_decision(f"http://localhost:{port}/apply", "example", method="POST", body={"delta": 1})
        agent.run(
            {
                "state:env.snapshot": _snapshot_payload(),
                "artifact:proposed.plan": _plan_payload([decision]),
            }
        )
        headers = RecordingHandler.capture[0]["headers"]
        assert "Idempotency-Key" in headers
        assert headers["Idempotency-Key"] == "idem-123"
    finally:
        server.shutdown()
        thread.join(timeout=1)
