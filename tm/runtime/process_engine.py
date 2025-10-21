from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from tm.dsl.runtime import Engine


class ProcessEngineError(RuntimeError):
    """Base class for ProcessEngine failures."""


class CapabilitiesMismatch(ProcessEngineError):
    """Raised when runtime capabilities do not satisfy requirements."""


class TransportError(ProcessEngineError):
    """Raised when the executor process dies or produces invalid JSON-RPC."""


@dataclass(frozen=True)
class ProcessEngineOptions:
    executor_path: Path
    python_path: Path = Path(sys.executable)
    required_steps: Optional[Iterable[str]] = None
    timeout: float = 5.0


class ProcessEngine(Engine):
    """Executes flows via an external executor using JSON-RPC over stdio."""

    name: str = "proc"

    def __init__(self, options: ProcessEngineOptions) -> None:
        self._options = options
        capabilities = self._fetch_capabilities()
        required = set(options.required_steps or ())
        missing = required - set(capabilities.get("step_kinds", ()))
        if missing:
            raise CapabilitiesMismatch(f"Missing runtime capabilities: {sorted(missing)}")

    def run_step(self, ctx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        raise ProcessEngineError("ProcessEngine does not implement incremental step execution")

    def start_run(
        self, ir: Dict[str, Any], inputs: Dict[str, Any], *, options: Optional[Dict[str, Any]] = None
    ) -> "ProcessRun":
        session = _ProcessSession(self._options)
        try:
            session.ensure_capabilities()
            payload = {
                "ir": ir,
                "inputs": inputs,
                "options": options or {},
            }
            response = session.call("Runtime.StartRun", payload)
            run_id = response.get("run_id")
            if not isinstance(run_id, str):
                raise ProcessEngineError("Executor returned invalid run identifier")
        except Exception:
            session.close()
            raise
        return ProcessRun(session=session, run_id=run_id)

    def poll(self, run: "ProcessRun") -> Dict[str, Any]:
        return run.poll()

    def cancel(self, run: "ProcessRun") -> Dict[str, Any]:
        return run.cancel()

    def _fetch_capabilities(self) -> Dict[str, Any]:
        session = _ProcessSession(self._options)
        try:
            result = session.call("Runtime.Capabilities", {})
            if not isinstance(result, dict):
                raise ProcessEngineError("Executor returned invalid capabilities payload")
            return result
        finally:
            session.close()


@dataclass
class ProcessRun:
    session: "_ProcessSession"
    run_id: str

    def poll(self) -> Dict[str, Any]:
        return self.session.call("Runtime.Poll", {"run_id": self.run_id})

    def cancel(self) -> Dict[str, Any]:
        try:
            return self.session.call("Runtime.Cancel", {"run_id": self.run_id})
        finally:
            self.session.close()

    def close(self) -> None:
        self.session.close()


class _ProcessSession:
    def __init__(self, options: ProcessEngineOptions) -> None:
        self._options = options
        try:
            self._proc = subprocess.Popen(
                [str(options.python_path), str(options.executor_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise TransportError(f"Failed to launch executor: {exc}") from exc
        if self._proc.stdin is None or self._proc.stdout is None:
            raise TransportError("Executor missing stdio pipes")
        self._stdin = self._proc.stdin
        self._stdout = self._proc.stdout
        self._responses: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._next_id = 1
        self._capabilities: Optional[Dict[str, Any]] = None

    def ensure_capabilities(self) -> Dict[str, Any]:
        if self._capabilities is not None:
            return self._capabilities
        self._capabilities = self.call("Runtime.Capabilities", {})
        return self._capabilities

    def call(self, method: str, params: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        message = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            self._stdin.write(message + "\n")
            self._stdin.flush()
        except Exception as exc:
            raise TransportError(f"Failed to write to executor: {exc}") from exc

        try:
            response = self._responses.get(timeout=timeout or self._options.timeout)
        except queue.Empty:
            raise TransportError(f"Executor timed out while calling {method}")

        if response.get("id") != request_id:
            raise TransportError("Executor returned mismatched response id")

        if "error" in response:
            error = response["error"]
            code = error.get("code")
            message = error.get("message", "executor error")
            data = error.get("data", {})
            if code in {3001, 3002}:
                raise TransportError(message)
            raise ProcessEngineError(f"{code}: {message} ({data})")

        result = response.get("result")
        if not isinstance(result, dict):
            raise TransportError("Executor returned invalid result payload")
        return result

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        try:
            self._proc.wait(timeout=0.2)
        except Exception:
            pass

    def _read_loop(self) -> None:
        while True:
            line = self._stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self._responses.put({"jsonrpc": "2.0", "id": None, "error": {"code": 3002, "message": "invalid JSON"}})
            else:
                self._responses.put(payload)


__all__ = [
    "ProcessEngine",
    "ProcessEngineOptions",
    "ProcessEngineError",
    "CapabilitiesMismatch",
    "TransportError",
]
