from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

from tm.runtime.workers import WorkerOptions, TaskWorkerSupervisor
from tm.triggers.config import TriggerConfigError, load_trigger_config
from tm.triggers.runner import TriggerRuntime


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TraceMind daemon supervisor")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--queue-dir", required=True)
    parser.add_argument("--idempotency-dir", required=True)
    parser.add_argument("--dlq-dir", required=True)
    parser.add_argument("--runtime", default="tm.app.wiring_flows:_runtime")
    parser.add_argument("--lease-ms", type=int, default=30_000)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--poll", type=float, default=0.5)
    parser.add_argument("--heartbeat", type=float, default=5.0)
    parser.add_argument("--heartbeat-timeout", type=float, default=15.0)
    parser.add_argument("--result-ttl", type=float, default=3600.0)
    parser.add_argument("--config", default="trace_config.toml")
    parser.add_argument("--drain-grace", type=float, default=10.0)
    parser.add_argument("--triggers-config", help="optional trigger configuration file")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    queue_dir = Path(args.queue_dir).resolve()
    queue_dir.mkdir(parents=True, exist_ok=True)
    idem_dir = Path(args.idempotency_dir).resolve()
    idem_dir.mkdir(parents=True, exist_ok=True)
    dlq_dir = Path(args.dlq_dir).resolve()
    dlq_dir.mkdir(parents=True, exist_ok=True)

    opts = WorkerOptions(
        worker_count=args.workers,
        queue_backend="file",
        queue_dir=str(queue_dir),
        idempotency_dir=str(idem_dir),
        dlq_dir=str(dlq_dir),
        runtime_spec=args.runtime,
        lease_ms=args.lease_ms,
        batch_size=args.batch,
        poll_interval=args.poll,
        heartbeat_interval=args.heartbeat,
        heartbeat_timeout=args.heartbeat_timeout,
        result_ttl=args.result_ttl,
        config_path=str(Path(args.config).resolve()) if args.config else None,
        drain_grace=args.drain_grace,
    )
    supervisor = TaskWorkerSupervisor(opts)

    trigger_runtime: Optional[TriggerRuntime] = None
    trigger_thread: Optional[threading.Thread] = None
    if args.triggers_config:
        config_path = Path(args.triggers_config).expanduser().resolve()
        try:
            cfg = load_trigger_config(str(config_path))
        except TriggerConfigError as exc:  # pragma: no cover - startup failure
            print(f"failed to load triggers: {exc}", file=sys.stderr)
            return 1
        trigger_runtime = TriggerRuntime(
            cfg,
            queue_dir=str(queue_dir),
            idempotency_dir=str(idem_dir),
            dlq_dir=str(dlq_dir),
        )

        def _run_triggers() -> None:
            asyncio.run(trigger_runtime.run())

        trigger_thread = threading.Thread(target=_run_triggers, name="tm-triggers", daemon=True)

    stop_event = threading.Event()

    def _shutdown(signum: int, _frame) -> None:
        if trigger_runtime is not None:
            trigger_runtime.request_stop()
        supervisor.drain(args.drain_grace)
        supervisor.stop()
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    supervisor.start()
    if trigger_thread is not None:
        trigger_thread.start()

    try:
        while not stop_event.wait(timeout=1.0):
            pass
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)

    if trigger_thread is not None and trigger_thread.is_alive():
        trigger_runtime.request_stop()  # type: ignore[union-attr]
        trigger_thread.join(timeout=2.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
