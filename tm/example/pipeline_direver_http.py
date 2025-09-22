"""Tiny HTTP driver to produce diverse payloads.
Run server (Hypercorn) first, then:
  python -m tm.examples.pipeline_drive_http --url https://localhost:8443 --insecure
"""
from __future__ import annotations
import argparse, json, time
import urllib.request, ssl

PAYLOADS = [
  {
    "kind": "NFProfile",
    "obj_id": "nf-1",
    "payload": {
      "nfInstanceId": "nf-1",
      "nfType": "NRF",
      "services": [{"name": " nrf-disc ", "state": "UP"}],
      "meta": {"version": 0}
    }
  },
  {
    "kind": "NFProfile",
    "obj_id": "nf-1",
    "payload": {
      "nfInstanceId": "nf-1",
      "nfType": "NRF",
      "services": [{"name": "nrf-disc", "state": "DOWN"}],
      "meta": {"version": 1}
    }
  },
  {
    "kind": "NFProfile",
    "obj_id": "nf-1",
    "payload": {
      "nfInstanceId": "nf-1",
      "nfType": "NRF",
      "status": "ALIVE",
      "services": [{"name": "nrf-disc", "state": "UP"}],
      "meta": {"version": 2},
      "policy": {"forceAlive": True}
    }
  }
]

def post(url: str, obj: dict, insecure: bool):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url + "/api/commands/upsert", data=body,
                                 headers={"content-type": "application/json"})
    ctx = None
    if insecure:
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx) as resp:
        print("status:", resp.status, resp.read().decode())

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--insecure", action="store_true")
    args = ap.parse_args()
    for p in PAYLOADS:
        post(args.url, p, args.insecure)
        time.sleep(0.05)