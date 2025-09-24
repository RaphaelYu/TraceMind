"""Minimal Kubernetes API client built on urllib."""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import parse, request, error


@dataclass
class K8sClient:
    """Very small Kubernetes client covering readiness, health, and pod listing."""

    base_url: str
    token: str
    ca_cert_path: Optional[str] = None
    insecure: bool = False

    def __post_init__(self) -> None:
        self._base_url = self.base_url.rstrip("/")
        self._ssl_context: Optional[ssl.SSLContext] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_pods(self, namespace: str, label_selector: Optional[str] = None) -> Dict[str, Any]:
        params = {}
        if label_selector:
            params["labelSelector"] = label_selector
        url = self._build_url(f"/api/v1/namespaces/{namespace}/pods", params)
        return self._request_json(url)

    def delete_pod(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        url = self._build_url(f"/api/v1/namespaces/{namespace}/pods/{pod_name}")
        return self._request_json(url, method="DELETE")

    def readyz(self) -> bool:
        return self._check_endpoint("/readyz")

    def healthz(self) -> bool:
        return self._check_endpoint("/healthz")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_url(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        rel = path.lstrip("/")
        url = parse.urljoin(self._base_url + "/", rel)
        if params:
            query = parse.urlencode(params)
            url = f"{url}?{query}"
        return url

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _get_ssl_context(self) -> Optional[ssl.SSLContext]:
        if self._base_url.startswith("http://"):
            return None
        if self._ssl_context is None:
            if self.insecure:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            elif self.ca_cert_path:
                ctx = ssl.create_default_context(cafile=self.ca_cert_path)
            else:
                ctx = ssl.create_default_context()
            self._ssl_context = ctx
        return self._ssl_context

    def _request_json(self, url: str, *, method: str = "GET", body: Optional[bytes] = None) -> Dict[str, Any]:
        data = self._request(url, method=method, body=body)
        if not data:
            return {}
        return json.loads(data)

    def _request(self, url: str, *, method: str = "GET", body: Optional[bytes] = None) -> str:
        req = request.Request(url, headers=self._headers(), method=method, data=body)
        ctx = self._get_ssl_context()
        try:
            with request.urlopen(req, context=ctx) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset)
        except error.HTTPError as exc:
            raise RuntimeError(f"K8s API error {exc.code}: {exc.reason}") from exc

    def _check_endpoint(self, path: str) -> bool:
        url = self._build_url(path)
        try:
            self._request(url)
            return True
        except RuntimeError:
            return False
