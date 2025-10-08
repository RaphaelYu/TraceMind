from __future__ import annotations

import asyncio
import importlib
import logging
import multiprocessing as mp
from multiprocessing import connection as mp_connection
import os
import signal
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from .idempotency import IdempotencyResult, IdempotencyStore
from .queue import FileWorkQueue, InMemoryWorkQueue, WorkQueue
from .queue.manager import ManagedLease, TaskQueueManager
from .dlq import DeadLetterStore
from .retry import load_retry_policy
from tm.obs import counters
from tm.kstore import DEFAULT_KSTORE_URL, KStore, open_kstore

LOGGER = logging.getLogger("tm.workers")

_TASK_PROCESSING_BUCKETS = [50, 100, 250, 500, 1000, 5000, float("inf")]
_END_TO_END_BUCKETS = [50, 100, 250, 500, 1000, 5000, float("inf")]


@dataclass
class WorkerOptions:
    worker_count: int = 1
    queue_backend: str = "file"  # file | memory
    queue_dir: Optional[str] = None
    idempotency_dir: Optional[str] = None
    runtime_spec: Optional[str] = None  # module:attr or module:function
    lease_ms: int = 30_000
    batch_size: int = 1
    poll_interval: float = 0.5
    heartbeat_interval: float = 5.0
    heartbeat_timeout: float = 15.0
    result_ttl: float = 3600.0
    dlq_dir: Optional[str] = None
    config_path: Optional[str] = None
    drain_grace: float = 10.0

    def validate(self) -> None:
        if self.worker_count <= 0:
            raise ValueError("worker_count must be positive")
        if self.queue_backend not in {"file", "memory"}:
            raise ValueError("queue_backend must be 'file' or 'memory'")
        if self.queue_backend == "memory" and self.worker_count > 1:
            raise ValueError("memory backend only supports a single worker")
        if self.queue_backend == "file" and not self.queue_dir:
            raise ValueError("queue_dir required for file backend")
        if self.queue_backend == "file" and not self.idempotency_dir:
            raise ValueError("idempotency_dir required for file backend")
        if self.queue_backend == "file" and not self.dlq_dir:
            raise ValueError("dlq_dir required for file backend")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")
        if self.heartbeat_timeout <= self.heartbeat_interval:
            raise ValueError("heartbeat_timeout must exceed heartbeat_interval")


@dataclass
class WorkerState:
    process: mp.Process
    conn: mp_connection.Connection
    last_heartbeat: float
    restarts: int = 0


def _load_runtime(spec: Optional[str]) -> Any:
    if not spec:
        raise RuntimeError("runtime_spec is required to start workers")
    module_name, _, attr = spec.partition(":")
    if not module_name:
        raise RuntimeError("runtime_spec must be module:attr or module:factory")
    module = importlib.import_module(module_name)
    target = getattr(module, attr) if attr else None
    if target is None:
        raise RuntimeError(f"runtime attribute '{attr}' not found in module '{module_name}'")
    if callable(target):
        runtime = target()
    else:
        runtime = target
    return runtime


def _make_queue(opts: WorkerOptions) -> WorkQueue:
    if opts.queue_backend == "memory":
        return InMemoryWorkQueue()
    queue_dir = opts.queue_dir or os.path.join(os.getcwd(), "data", "queue")
    return FileWorkQueue(queue_dir)


def _make_idempotency_store(opts: WorkerOptions) -> IdempotencyStore:
    if opts.queue_backend == "memory":
        return IdempotencyStore(dir_path=opts.idempotency_dir or os.path.join(os.getcwd(), "data", "idem"))
    if not opts.idempotency_dir:
        raise RuntimeError("idempotency_dir required for file backend")
    return IdempotencyStore(dir_path=opts.idempotency_dir)


def _serialize_result(result: Mapping[str, Any]) -> IdempotencyResult:
    status = str(result.get("status", "ok"))
    error_payload = None
    if status != "ok":
        error_payload = {
            "error_code": result.get("error_code"),
            "error_message": result.get("error_message"),
        }
    return IdempotencyResult(status=status, output=dict(result), error=error_payload)


def _send_heartbeat(conn: mp_connection.Connection, worker_id: int, ts: Optional[float] = None) -> None:
    payload = ("heartbeat", worker_id, ts if ts is not None else time.monotonic())
    try:
        conn.send(payload)
    except Exception:  # pragma: no cover - connection closed
        LOGGER.debug("worker %s failed to emit heartbeat", worker_id, exc_info=True)


def _worker_entry(
    worker_id: int,
    opts: WorkerOptions,
    control_conn: mp_connection.Connection,
) -> None:
    async def _async_worker() -> None:
        queue_impl = _make_queue(opts)
        id_store = _make_idempotency_store(opts)
        dlq_dir = opts.dlq_dir or os.path.join(os.getcwd(), "data", "dlq")
        dlq_store = DeadLetterStore(dlq_dir)
        retry_policy = load_retry_policy(opts.config_path)
        manager = TaskQueueManager(
            queue_impl,
            id_store,
            dead_letters=dlq_store,
            retry_policy=retry_policy,
            default_ttl=opts.result_ttl,
        )
        runtime = _load_runtime(opts.runtime_spec)
        lease_ms = opts.lease_ms
        batch_size = opts.batch_size
        poll_interval = opts.poll_interval
        heartbeat_interval = opts.heartbeat_interval
        next_heartbeat = 0.0
        draining = False
        drain_deadline: Optional[float] = None
        try:
            while True:
                shutdown_requested = False
                while control_conn.poll():
                    msg = control_conn.recv()
                    if not isinstance(msg, tuple) or not msg:
                        continue
                    kind = msg[0]
                    if kind == "shutdown":
                        shutdown_requested = True
                        break
                    if kind == "drain":
                        draining = True
                        grace = float(msg[1]) if len(msg) > 1 else opts.drain_grace
                        drain_deadline = time.monotonic() + max(0.0, grace)
                if shutdown_requested:
                    break
                now = time.monotonic()
                if now >= next_heartbeat:
                    _send_heartbeat(control_conn, worker_id, now)
                    next_heartbeat = now + heartbeat_interval
                if draining:
                    if drain_deadline is not None and now >= drain_deadline:
                        break
                leases = manager.lease(batch_size, lease_ms)
                if not leases:
                    if draining:
                        break
                    await asyncio.sleep(poll_interval)
                    continue
                for lease in leases:
                    await _process_lease(manager, runtime, lease, control_conn, worker_id)
                if draining:
                    break
        finally:
            try:
                queue_impl.flush()
            except Exception:  # pragma: no cover - best effort
                pass
            try:
                queue_impl.close()
            except Exception:  # pragma: no cover - best effort
                pass
            close = getattr(runtime, "aclose", None)
            if callable(close):
                try:
                    await close()
                except Exception:  # pragma: no cover - best effort
                    pass
            try:
                control_conn.close()
            except Exception:  # pragma: no cover
                pass

    asyncio.run(_async_worker())


async def _process_lease(
    manager: TaskQueueManager,
    runtime: Any,
    lease: ManagedLease,
    control_conn: mp_connection.Connection,
    worker_id: int,
) -> None:
    envelope = lease.envelope
    processing_start = time.perf_counter()

    def _observe(status: str) -> None:
        duration_ms = (time.perf_counter() - processing_start) * 1000.0
        counters.metrics.get_histogram(
            "tm_task_processing_ms",
            help="Task execution duration in milliseconds",
            buckets=_TASK_PROCESSING_BUCKETS,
        ).observe(duration_ms, labels={"flow": envelope.flow_id, "status": status})
        end_to_end_ms = max(0.0, (time.time() - envelope.scheduled_at) * 1000.0)
        counters.metrics.get_histogram(
            "tm_end_to_end_ms",
            help="End-to-end task latency in milliseconds",
            buckets=_END_TO_END_BUCKETS,
        ).observe(end_to_end_ms, labels={"flow": envelope.flow_id, "status": status})

    cached = manager.get_cached_result(envelope)
    if cached is not None:
        manager.ack(lease)
        _send_heartbeat(control_conn, worker_id)
        _observe("cached")
        return

    try:
        result = await runtime.run(envelope.flow_id, inputs=envelope.input)
    except Exception as exc:  # pragma: no cover - runtime failure path
        LOGGER.exception("worker-%s flow %s failed: %s", worker_id, envelope.flow_id, exc)
        error_payload = {
            "error_code": "RUNTIME_EXCEPTION",
            "error_message": str(exc),
            "retryable": True,
        }
        manager.handle_failure(lease, error=error_payload)
        _observe("error")
        return

    status = result.get("status") if isinstance(result, Mapping) else None
    if status != "ok":
        error_payload = {
            "error_code": result.get("error_code") if isinstance(result, Mapping) else None,
            "error_message": result.get("error_message") if isinstance(result, Mapping) else "task error",
            "retryable": result.get("retryable", True) if isinstance(result, Mapping) else True,
        }
        manager.handle_failure(lease, error=error_payload)
        _observe("error")
        return

    manager.ack(lease)
    try:
        manager.record_result(envelope, _serialize_result(result))
    except Exception:  # pragma: no cover - cache failure should not crash worker
        LOGGER.exception("worker-%s failed to record idempotent result", worker_id)
    _send_heartbeat(control_conn, worker_id)
    _observe("ok")


class TaskWorkerSupervisor:
    def __init__(self, options: WorkerOptions) -> None:
        self._opts = options
        self._opts.validate()
        ctx = mp.get_context("spawn")
        self._ctx = ctx
        self._states: Dict[int, WorkerState] = {}
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._draining = threading.Event()
        url = os.getenv("TM_KSTORE", DEFAULT_KSTORE_URL)
        self._kstore_url = url
        self._kstore: KStore | None = open_kstore(url)
        self._kstore_closed = False

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._kstore_closed or self._kstore is None:
            self._kstore = open_kstore(self._kstore_url)
            self._kstore_closed = False
        if self._running:
            return
        self._running = True
        for worker_id in range(self._opts.worker_count):
            self._spawn_worker(worker_id)
        self._monitor_thread = threading.Thread(target=self._monitor_loop, name="tm-worker-monitor", daemon=True)
        self._monitor_thread.start()

    def stop(self, grace_period: float = 5.0) -> None:
        if not self._running:
            return
        self.drain(grace_period)
        self._running = False
        with self._lock:
            states = list(self._states.items())
        for _, state in states:
            try:
                state.conn.send(("shutdown",))
            except Exception:  # pragma: no cover
                pass
        deadline = time.time() + grace_period
        for _, state in states:
            state.process.join(timeout=max(0.0, deadline - time.time()))
        with self._lock:
            for worker_id, state in list(self._states.items()):
                if state.process.is_alive():
                    state.process.terminate()
                    state.process.join(timeout=1.0)
                try:
                    state.conn.close()
                except Exception:  # pragma: no cover
                    pass
            self._states.clear()
        self._record_worker_metrics()
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=1.0)
            self._monitor_thread = None
        if self._kstore is not None:
            try:
                self._kstore.close()
            except Exception:  # pragma: no cover - best effort
                pass
            finally:
                self._kstore = None
                self._kstore_closed = True

    def run_forever(self) -> None:  # pragma: no cover - CLI utility
        self.start()
        try:
            while self._running:
                time.sleep(1.0)
        except KeyboardInterrupt:
            LOGGER.info("shutdown requested (keyboard interrupt)")
            self.stop()

    @property
    def kstore(self) -> KStore:
        if self._kstore is None:
            raise RuntimeError("knowledge store is closed")
        return self._kstore

    def status(self) -> Dict[int, Dict[str, Any]]:
        with self._lock:
            return {
                worker_id: {
                    "pid": state.process.pid,
                    "alive": state.process.is_alive(),
                    "last_heartbeat": state.last_heartbeat,
                    "restarts": state.restarts,
                    "conn_closed": state.conn.closed,
                }
                for worker_id, state in self._states.items()
            }

    # ------------------------------------------------------------------
    def drain(self, grace_period: Optional[float] = None) -> None:
        if not self._running:
            return
        grace = grace_period if grace_period is not None else self._opts.drain_grace
        self._draining.set()
        try:
            with self._lock:
                states = list(self._states.items())
            for _, state in states:
                try:
                    state.conn.send(("drain", grace))
                except Exception:  # pragma: no cover
                    pass
            deadline = time.time() + grace
            for _, state in states:
                remaining = max(0.0, deadline - time.time())
                state.process.join(timeout=remaining)
            with self._lock:
                for worker_id, state in list(self._states.items()):
                    if state.process.is_alive():
                        continue
                    try:
                        state.conn.close()
                    except Exception:  # pragma: no cover
                        pass
                    self._states.pop(worker_id, None)
            self._record_worker_metrics()
        finally:
            self._draining.clear()

    def _spawn_worker(self, worker_id: int, *, restarts: int = 0) -> None:
        parent_conn, child_conn = self._ctx.Pipe(duplex=True)
        proc = self._ctx.Process(
            target=_worker_entry,
            args=(worker_id, self._opts, child_conn),
            name=f"tm-worker-{worker_id}",
        )
        proc.daemon = False
        proc.start()
        child_conn.close()
        with self._lock:
            self._states[worker_id] = WorkerState(
                process=proc,
                conn=parent_conn,
                last_heartbeat=time.monotonic(),
                restarts=restarts,
            )
        LOGGER.info("started worker %s pid=%s restarts=%s", worker_id, proc.pid, restarts)
        self._record_worker_metrics()

    def _monitor_loop(self) -> None:
        while True:
            if not self._running and not self._states:
                break
            with self._lock:
                snapshot = list(self._states.items())
            conns = [state.conn for _, state in snapshot if not state.conn.closed]
            if conns:
                try:
                    ready = mp_connection.wait(conns, timeout=0.5)
                except Exception:  # pragma: no cover - wait failure fallback
                    ready = []
                for conn in ready:
                    try:
                        msg = conn.recv()
                    except (EOFError, OSError):
                        continue
                    if isinstance(msg, tuple) and msg and msg[0] == "heartbeat":
                        worker_id = self._find_worker_id(conn)
                        if worker_id is None:
                            continue
                        ts = float(msg[2]) if len(msg) > 2 else time.monotonic()
                        with self._lock:
                            state = self._states.get(worker_id)
                            if state:
                                state.last_heartbeat = ts
            else:
                time.sleep(0.2)
            self._check_workers()

    def _check_workers(self) -> None:
        if not self._running:
            return
        now = time.monotonic()
        with self._lock:
            states_snapshot = list(self._states.items())
        for worker_id, state in states_snapshot:
            proc = state.process
            if not proc.is_alive():
                if self._draining.is_set():
                    continue
                LOGGER.warning("worker %s exited unexpectedly; restarting", worker_id)
                self._restart_worker(worker_id)
                continue
            if now - state.last_heartbeat > self._opts.heartbeat_timeout:
                if self._draining.is_set():
                    continue
                LOGGER.warning("worker %s heartbeat stale; restarting", worker_id)
                try:
                    state.conn.send(("shutdown",))
                except Exception:  # pragma: no cover
                    pass
                if proc.is_alive():
                    try:
                        proc.terminate()
                    except Exception:  # pragma: no cover
                        LOGGER.exception("failed to terminate unresponsive worker %s", worker_id)
                self._restart_worker(worker_id)
        self._record_worker_metrics()

    def _restart_worker(self, worker_id: int) -> None:
        if not self._running:
            return
        with self._lock:
            old_state = self._states.pop(worker_id, None)
        restarts = (old_state.restarts + 1) if old_state else 1
        if old_state:
            try:
                old_state.conn.close()
            except Exception:  # pragma: no cover
                pass
            if old_state.process.is_alive():
                old_state.process.join(timeout=0.5)
        self._spawn_worker(worker_id, restarts=restarts)
        self._record_worker_metrics()

    def _find_worker_id(self, conn: mp_connection.Connection) -> Optional[int]:
        with self._lock:
            for worker_id, state in self._states.items():
                if state.conn == conn:
                    return worker_id
        return None

    def _record_worker_metrics(self) -> None:
        with self._lock:
            live = sum(1 for state in self._states.values() if state.process.is_alive())
        counters.metrics.get_gauge(
            "tm_workers_live",
            help="Active worker processes",
        ).set(float(live))


def install_signal_handlers(supervisor: TaskWorkerSupervisor) -> None:  # pragma: no cover - CLI
    def _handle(signum: int, _frame: Any) -> None:
        LOGGER.info("received signal %s; initiating shutdown", signum)
        supervisor.drain()
        supervisor.stop()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


__all__ = [
    "WorkerOptions",
    "TaskWorkerSupervisor",
    "install_signal_handlers",
]
