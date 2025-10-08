from __future__ import annotations
from typing import Any, Dict, List, Tuple
import time
import uuid
import json


class AirflowStyleTracer:
    def __init__(self, dag_id_prefix: str = "tm_flow", capture_outputs: bool = True, xcom_bytes_limit: int = 16_000):
        self.dag_id_prefix = dag_id_prefix
        self.capture_outputs = capture_outputs
        self.xcom_bytes_limit = xcom_bytes_limit
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._tis: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[str, List[Tuple[str, str]]] = {}

    def begin(self, flow_name: str) -> str:
        run_id = f"af_{uuid.uuid4().hex}"
        now = time.time()
        dag_id = f"{self.dag_id_prefix}.{flow_name}"
        self._runs[run_id] = {
            "dag_id": dag_id,
            "run_id": run_id,
            "start_date": now,
            "end_date": None,
            "state": "running",
        }
        self._tis[run_id] = {}
        self._edges.setdefault(run_id, [])
        return run_id

    def on_step(self, run_id: str, step, result, inputs: Dict[str, Any]):
        ti = {
            "dag_id": self._runs[run_id]["dag_id"],
            "run_id": run_id,
            "task_id": step.id,
            "state": "success" if result.status == "ok" else "failed",
            "duration": result.duration_ms / 1000.0,
            "operator": step.uses,
            "kind": step.kind.name,
            "in": inputs,
            "out": None,
        }
        if self.capture_outputs and result.output is not None:
            s = json.dumps(result.output, ensure_ascii=False)
            ti["out"] = {"truncated": True, "size": len(s)} if len(s) > self.xcom_bytes_limit else result.output
        self._tis[run_id][step.id] = ti

    def end(self, run_id: str, status: str):
        self._runs[run_id]["end_date"] = time.time()
        self._runs[run_id]["state"] = "success" if status == "ok" else "failed"

    def record_edges(self, run_id: str, edges: List[Tuple[str, str]]):
        self._edges[run_id] = list(edges)

    def get_run(self, run_id: str):
        return self._runs.get(run_id, {}), list(self._tis.get(run_id, {}).values()), self._edges.get(run_id, [])
