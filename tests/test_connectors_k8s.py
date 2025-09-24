import json

import pytest

from tm.connectors.k8s import K8sClient


class DummyResponse:
    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")
        self.headers = _Headers()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _Headers:
    def get_content_charset(self) -> str:
        return "utf-8"


def test_k8s_client_get_pods_and_health(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_urlopen(req, context=None):  # noqa: ANN001
        url = req.full_url
        method = req.method or req.get_method()
        captured.setdefault("urls", []).append((method, url))
        captured.setdefault("auth", req.headers.get("Authorization"))
        if "/pods" in url and method == "GET":
            payload = {"items": [{"metadata": {"name": "demo"}}]}
            return DummyResponse(json.dumps(payload))
        if url.endswith("/readyz") or url.endswith("/healthz"):
            return DummyResponse("ok")
        if method == "DELETE" and "/pods/" in url:
            payload = {"status": "deleted"}
            return DummyResponse(json.dumps(payload))
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr("tm.connectors.k8s.request.urlopen", fake_urlopen)

    client = K8sClient(base_url="https://cluster", token="test-token", insecure=True)

    pods = client.get_pods("default", label_selector="app=demo")
    assert pods["items"][0]["metadata"]["name"] == "demo"
    assert captured["auth"] == "Bearer test-token"

    assert client.readyz() is True
    assert client.healthz() is True

    deleted = client.delete_pod("default", "demo")
    assert deleted["status"] == "deleted"
    assert any(method == "DELETE" for method, _ in captured["urls"])
