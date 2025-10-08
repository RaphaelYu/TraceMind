"""Tiny Docker HTTP client supporting either TCP or Unix sockets."""

from __future__ import annotations

import http.client
import json
import socket
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import parse


class _UnixHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection variant that tunnels over a Unix domain socket."""

    def __init__(self, socket_path: str):
        super().__init__("localhost")
        self._socket_path = socket_path

    def connect(self) -> None:  # type: ignore[override]
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self._socket_path)
        self.sock = sock


@dataclass
class DockerClient:
    base_url: Optional[str] = None
    unix_socket: str = "/var/run/docker.sock"

    def __post_init__(self) -> None:
        self._parsed = parse.urlparse(self.base_url) if self.base_url else None

    # ------------------------------------------------------------------
    def list_containers(self, all: bool = False) -> Any:
        params = {"all": "1" if all else "0"}
        return self._request_json("GET", "/containers/json", params=params)

    def restart(self, container_id: str) -> bool:
        status = self._request("POST", f"/containers/{container_id}/restart", expect_json=False)
        return status < 300

    def ping(self) -> bool:
        try:
            status = self._request("GET", "/_ping", expect_json=False)
            return isinstance(status, int) and status < 400
        except RuntimeError:
            return False

    # ------------------------------------------------------------------
    def _request_json(self, method: str, path: str, params: Optional[Dict[str, str]] = None) -> Any:
        status, payload = self._perform(method, path, params=params)
        if status >= 400:
            raise RuntimeError(f"Docker API error {status}")
        return json.loads(payload) if payload else None

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        expect_json: bool = True,
    ) -> int | str:
        status, payload = self._perform(method, path, params=params, body=body, headers=headers)
        if status >= 400:
            raise RuntimeError(f"Docker API error {status}")
        return status if not expect_json else payload

    def _perform(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[int, str]:
        headers = headers or {}
        target_path = self._build_path(path, params)

        if self._parsed:
            conn = self._http_conn()
        else:
            conn = _UnixHTTPConnection(self.unix_socket)

        try:
            conn.request(method, target_path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            return resp.status, data
        finally:
            conn.close()

    def _build_path(self, path: str, params: Optional[Dict[str, str]]) -> str:
        base_path = self._parsed.path if self._parsed else ""
        rel = path.lstrip("/")
        full = base_path.rstrip("/") + "/" + rel if base_path else "/" + rel
        if params:
            return f"{full}?{parse.urlencode(params)}"
        return full

    def _http_conn(self) -> http.client.HTTPConnection:
        assert self._parsed is not None
        scheme = self._parsed.scheme or "http"
        host = self._parsed.hostname or "localhost"
        port = self._parsed.port
        if scheme == "https":
            return http.client.HTTPSConnection(host, port)
        return http.client.HTTPConnection(host, port)
