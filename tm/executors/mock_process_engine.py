from __future__ import annotations

import json
import queue
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class RunState:
    ir: Dict[str, Any]
    inputs: Dict[str, Any]
    status: str = "pending"
    events: list[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class MockExecutor:
    def __init__(self) -> None:
        self._runs: Dict[str, RunState] = {}
        self._lock = threading.Lock()

    def capabilities(self) -> Dict[str, Any]:
        return {
            "version": "0.1.0",
            "step_kinds": [
                "opcua.read",
                "opcua.write",
                "policy.apply",
                "dsl.emit",
            ],
            "limits": {"concurrency": 1},
        }

    def start_run(self, ir: Dict[str, Any], inputs: Dict[str, Any], opts: Dict[str, Any]) -> Dict[str, Any]:
        run_id = opts.get("run_id") or uuid.uuid4().hex
        state = RunState(ir=ir, inputs=inputs, status="running")
        state.events.append(
            {
                "type": "log",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "level": "info",
                "message": "run started",
            }
        )
        with self._lock:
            self._runs[run_id] = state
        threading.Thread(target=self._complete, args=(run_id,), daemon=True).start()
        return {"run_id": run_id}

    def _complete(self, run_id: str) -> None:
        time.sleep(0.05)
        with self._lock:
            state = self._runs.get(run_id)
            if state is None:
                return
            state.status = "completed"
            state.events.append(
                {
                    "type": "log",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                    "level": "info",
                    "message": "run completed",
                }
            )

    def poll(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None:
                return {"status": "failed", "events": [], "summary": {"error": "unknown run"}}
            events = list(state.events)
            state.events.clear()
            return {
                "status": state.status,
                "events": events,
                "summary": {"run_id": run_id},
            }

    def cancel(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None:
                return {"ok": False}
            state.status = "failed"
        return {"ok": True}

    def health(self) -> Dict[str, Any]:
        return {"ok": True}


def main() -> None:
    executor = MockExecutor()
    request_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

    def reader() -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            request_queue.put(payload)

    threading.Thread(target=reader, daemon=True).start()

    while True:
        try:
            request = request_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        response = _handle_request(executor, request)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def _handle_request(executor: MockExecutor, request: Dict[str, Any]) -> Dict[str, Any]:
    method = request.get("method")
    req_id = request.get("id")

    try:
        if method == "Runtime.Capabilities":
            result = executor.capabilities()
        elif method == "Runtime.StartRun":
            params = request.get("params", {})
            result = executor.start_run(params.get("ir", {}), params.get("inputs", {}), params.get("options", {}))
        elif method == "Runtime.Poll":
            params = request.get("params", {})
            result = executor.poll(params.get("run_id"))
        elif method == "Runtime.Cancel":
            params = request.get("params", {})
            result = executor.cancel(params.get("run_id"))
        elif method == "Runtime.Health":
            result = executor.health()
        else:
            raise ValueError(f"Unsupported method {method}")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": 3002,
                "message": str(exc),
                "data": {"retriable": False},
            },
        }


if __name__ == "__main__":
    main()
