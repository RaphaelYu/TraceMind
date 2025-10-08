# tm/cli.py
import argparse
import fnmatch
import json
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

try:
    import yaml
except ModuleNotFoundError:  # optional dependency; commands that need it will check explicitly
    yaml = None
from tm.app.demo_plan import build_plan
from tm.pipeline.analysis import analyze_plan
from tm.obs.retrospect import load_window
from tm.scaffold import create_flow, create_policy, init_project, find_project_root
from tm.run_recipe import run_recipe
from tm.governance.audit import AuditTrail
from tm.governance.config import load_governance_config
from tm.governance.hitl import HitlManager
from tm.runtime.workers import WorkerOptions, TaskWorkerSupervisor, install_signal_handlers
from tm.runtime.dlq import DeadLetterStore
from tm.runtime.queue import FileWorkQueue, InMemoryWorkQueue
from tm.runtime.idempotency import IdempotencyStore
from tm.runtime.queue.manager import TaskQueueManager
from tm.runtime.retry import load_retry_policy

__path__ = [str(Path(__file__).with_name("cli"))]
from tm.cli.plugin_verify import run as plugin_verify_run
from tm.cli.flow import register_flow_commands
from tm.cli.validate import register_validate_command
from tm.cli.simulate import register_simulate_command

_TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "templates"


def _cli_version() -> str:
    try:
        return importlib_metadata.version("trace-mind")
    except importlib_metadata.PackageNotFoundError:
        return "trace-mind (development)"
    except Exception:
        return "trace-mind (unknown)"


def _init_from_template(template: str, project_name: str, *, force: bool) -> Path:
    template_dir = _TEMPLATE_ROOT / template
    if not template_dir.is_dir():
        raise FileNotFoundError(f"Unknown template '{template}'")
    project_root = Path.cwd() / project_name
    if project_root.exists():
        if not project_root.is_dir():
            raise FileExistsError(f"Destination '{project_root}' exists and is not a directory")
        if not force and any(project_root.iterdir()):
            raise FileExistsError(
                f"Destination '{project_root}' already exists; use --force to overwrite scaffolding files"
            )
    else:
        project_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template_dir, project_root, dirs_exist_ok=True)
    return project_root


def _cmd_pipeline_analyze(args):
    plan = build_plan()
    focus = args.focus or []
    rep = analyze_plan(plan, focus_fields=focus)

    # Print summary
    print("== Step dependency topo ==")
    if rep.graphs.topo:
        print(" -> ".join(rep.graphs.topo))
    else:
        print("CYCLES detected:")
        for cyc in rep.graphs.cycles:
            print("  - " + " -> ".join(cyc))

    print("\n== Conflicts ==")
    if not rep.conflicts:
        print("  (none)")
    else:
        for c in rep.conflicts:
            print(f"  [{c.kind}] where={c.where} a={c.a} b={c.b} detail={c.detail}")

    print("\n== Coverage ==")
    print("  unused_steps:", rep.coverage.unused_steps or "[]")
    print("  empty_rules:", rep.coverage.empty_rules or "[]")
    print("  empty_triggers:", rep.coverage.empty_triggers or "[]")
    if rep.coverage.focus_uncovered:
        print("  focus_uncovered:", rep.coverage.focus_uncovered)


def _cmd_pipeline_export_dot(args):
    plan = build_plan()
    rep = analyze_plan(plan)
    with open(args.out_rules_steps, "w", encoding="utf-8") as f:
        f.write(rep.dot_rules_steps)
    with open(args.out_step_deps, "w", encoding="utf-8") as f:
        f.write(rep.dot_step_deps)
    print("DOT files written:", args.out_rules_steps, "and", args.out_step_deps)


def _build_hitl_manager(config_path: str) -> HitlManager:
    cfg = load_governance_config(config_path)
    hitl_cfg = cfg.hitl
    if not hitl_cfg.enabled:
        raise RuntimeError("HITL approvals are disabled in configuration")
    return HitlManager(hitl_cfg, audit=AuditTrail(cfg.audit))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tm", description="TraceMind CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_cli_version()}")
    sub = parser.add_subparsers(dest="cmd")

    plugin_parser = sub.add_parser("plugin", help="plugin tools")
    plugin_sub = plugin_parser.add_subparsers(dest="pcmd")
    plugin_verify = plugin_sub.add_parser("verify", help="verify plugin conformance")
    plugin_verify.add_argument("group")
    plugin_verify.add_argument("name")
    plugin_verify.set_defaults(func=plugin_verify_run)

    sp = sub.add_parser("pipeline", help="pipeline tools")
    ssp = sp.add_subparsers(dest="pcmd")

    sp_an = ssp.add_parser("analyze", help="analyze current plan")
    sp_an.add_argument("--focus", nargs="*", help="fields to check coverage (e.g. services[].state status)")
    sp_an.set_defaults(func=_cmd_pipeline_analyze)

    sp_dot = ssp.add_parser("export-dot", help="export DOT graphs")
    sp_dot.add_argument("--out-rules-steps", required=True, help="output .dot for rule->steps")
    sp_dot.add_argument("--out-step-deps", required=True, help="output .dot for step dependency graph")
    sp_dot.set_defaults(func=_cmd_pipeline_export_dot)

    def _parse_duration(expr: str) -> timedelta:
        units = {"s": 1, "m": 60, "h": 3600}
        suffix = expr[-1:]
        if suffix not in units:
            raise ValueError(f"Invalid duration '{expr}'")
        try:
            value = float(expr[:-1])
        except ValueError as exc:
            raise ValueError(f"Invalid duration '{expr}'") from exc
        return timedelta(seconds=value * units[suffix])

    def _cmd_metrics_dump(args):
        window = _parse_duration(args.window)
        until = datetime.now(timezone.utc)
        since = until - window
        entries = load_window(args.dir, since, until)
        if args.format == "csv":
            print("type,name,labels,value")
            for entry in entries:
                label_str = ";".join(f"{k}={v}" for k, v in sorted(entry["labels"].items()))
                print(f"{entry['type']},{entry['name']},{label_str},{entry['value']}")
        else:
            print(json.dumps(entries, indent=2))

    sp_metrics = sub.add_parser("metrics", help="metrics tools")
    spm_sub = sp_metrics.add_subparsers(dest="mcmd")
    spm_dump = spm_sub.add_parser("dump", help="dump metrics window")
    spm_dump.add_argument("--dir", required=True, help="binlog directory")
    spm_dump.add_argument("--window", default="5m", help="window size (e.g. 5m, 1h)")
    spm_dump.add_argument("--format", choices=["csv", "json"], default="csv")
    spm_dump.set_defaults(func=_cmd_metrics_dump)

    approve_parser = sub.add_parser("approve", help="manage human approvals")
    approve_parser.add_argument("--config", default="trace-mind.toml", help="governance config path")
    approve_parser.add_argument("--list", action="store_true", help="list pending approvals")
    approve_parser.add_argument("approval_id", nargs="?", help="approval identifier")
    approve_parser.add_argument("--decision", choices=["approve", "deny"], help="decision to apply")
    approve_parser.add_argument("--actor", default="cli", help="actor identifier")
    approve_parser.add_argument("--note", help="optional note")

    def _cmd_approve(args):
        try:
            manager = _build_hitl_manager(args.config)
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)

        if args.list:
            records = manager.pending()
            if not records:
                print("(no pending approvals)")
                return
            for record in records:
                print(
                    json.dumps(
                        {
                            "approval_id": record.approval_id,
                            "flow": record.flow,
                            "step": record.step,
                            "reason": record.reason,
                            "actors": list(record.actors),
                            "created_at": record.created_at,
                            "ttl_ms": record.ttl_ms,
                        },
                        ensure_ascii=False,
                    )
                )
            return

        if not args.approval_id or not args.decision:
            print("approval_id and --decision are required unless using --list", file=sys.stderr)
            sys.exit(1)

        try:
            record = manager.decide(
                args.approval_id,
                decision=args.decision,
                actor=args.actor or "cli",
                note=args.note,
            )
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(
                json.dumps(
                    {
                        "approval_id": record.approval_id,
                        "decision": record.status,
                        "actor": record.decided_by,
                        "note": record.note,
                    },
                    ensure_ascii=False,
                )
            )

    approve_parser.set_defaults(func=_cmd_approve)

    init_parser = sub.add_parser("init", help="initialize a new TraceMind project")
    init_parser.add_argument("project_name", help="project directory to create")
    init_parser.add_argument("--with-prom", action="store_true", help="include Prometheus hook scaffold")
    init_parser.add_argument("--with-retrospect", action="store_true", help="include Retrospect exporter scaffold")
    init_parser.add_argument("--force", action="store_true", help="overwrite existing scaffold files")
    init_parser.add_argument("--template", choices=["minimal", "recipe-only"], help="use a project template")

    def _cmd_init(args):
        try:
            if args.template:
                _init_from_template(args.template, args.project_name, force=args.force)
            else:
                init_project(
                    args.project_name,
                    Path.cwd(),
                    with_prom=args.with_prom,
                    with_retrospect=args.with_retrospect,
                    force=args.force,
                )
        except (FileExistsError, FileNotFoundError) as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Project '{args.project_name}' ready")

    init_parser.set_defaults(func=_cmd_init)

    new_parser = sub.add_parser("new", help="generate project assets")
    new_sub = new_parser.add_subparsers(dest="asset")

    flow_parser = new_sub.add_parser("flow", help="create a flow skeleton")
    flow_parser.add_argument("flow_name", help="flow name")
    variant = flow_parser.add_mutually_exclusive_group()
    variant.add_argument("--switch", action="store_true", help="include a switch step")
    variant.add_argument("--parallel", action="store_true", help="include a parallel step")

    def _cmd_new_flow(args):
        try:
            root = find_project_root(Path.cwd())
            created = create_flow(args.flow_name, project_root=root, switch=args.switch, parallel=args.parallel)
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Flow created: {created.relative_to(root)}")

    flow_parser.set_defaults(func=_cmd_new_flow)

    policy_parser = new_sub.add_parser("policy", help="create a policy skeleton")
    policy_parser.add_argument("policy_name", help="policy identifier")
    strategy = policy_parser.add_mutually_exclusive_group()
    strategy.add_argument("--epsilon", action="store_true", help="generate epsilon-greedy policy")
    strategy.add_argument("--ucb", action="store_true", help="generate UCB policy")
    policy_parser.add_argument("--mcp-endpoint", help="default MCP endpoint", default=None)

    def _cmd_new_policy(args):
        try:
            root = find_project_root(Path.cwd())
            strat = "ucb" if args.ucb else "epsilon"
            created = create_policy(args.policy_name, project_root=root, strategy=strat, mcp_endpoint=args.mcp_endpoint)
        except Exception as exc:  # pragma: no cover - CLI error path
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Policy created: {created.relative_to(root)}")

    policy_parser.set_defaults(func=_cmd_new_policy)

    run_parser = sub.add_parser("run", help="execute a flow recipe")
    run_parser.add_argument("recipe", help="path to recipe (JSON or YAML)")
    run_parser.add_argument("-i", "--input", help="JSON string or @file with initial state")

    def _cmd_run(args):
        payload: Dict[str, Any]
        if args.input:
            raw = args.input
            if raw.startswith("@"):
                data = Path(raw[1:]).read_text(encoding="utf-8")
            else:
                data = raw
            try:
                payload_obj = json.loads(data)
            except json.JSONDecodeError as exc:  # pragma: no cover - CLI error path
                print(f"Invalid input JSON: {exc}", file=sys.stderr)
                sys.exit(1)
            if not isinstance(payload_obj, dict):
                print("Input JSON must decode to an object", file=sys.stderr)
                sys.exit(1)
            payload = payload_obj
        else:
            payload = {}

        result = run_recipe(Path(args.recipe), payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    run_parser.set_defaults(func=_cmd_run)

    def _load_json_arg(value: str, *, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if value is None:
            return default or {}
        raw = value
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, Mapping):
            raise ValueError("JSON payload must be an object")
        return dict(data)

    enqueue_parser = sub.add_parser(
        "enqueue",
        help="enqueue a flow run",
        description="Enqueue a flow invocation for background workers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm enqueue flows/hello.yaml -i '{\"name\":\"world\"}'""",
    )
    enqueue_parser.add_argument("flow", help="Flow id or YAML spec path containing flow.id")
    enqueue_parser.add_argument("-i", "--input", default="{}", help="JSON payload or @file path")
    enqueue_parser.add_argument("--queue", choices=["file", "memory"], default="file", help="queue backend")
    enqueue_parser.add_argument("--queue-dir", default="data/queue", help="queue directory (file backend)")
    enqueue_parser.add_argument(
        "--idempotency-dir",
        default="data/idempotency",
        help="idempotency cache directory",
    )
    enqueue_parser.add_argument("--idempotency-key", help="set idempotency key header")
    enqueue_parser.add_argument("--headers", help="additional headers JSON or @file")
    enqueue_parser.add_argument("--trace", help="trace metadata JSON or @file")

    def _resolve_flow_id(arg: str) -> str:
        path = Path(arg)
        if path.is_file():
            if yaml is None:
                raise RuntimeError(
                    "PyYAML is required to load flow specifications; install the 'yaml' extra, e.g. `pip install trace-mind[yaml]`."
                )
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise ValueError(f"Failed to parse flow spec at {path}: {exc}") from exc
            if isinstance(data, Mapping):
                flow = data.get("flow")
                if isinstance(flow, Mapping):
                    flow_id = flow.get("id")
                    if isinstance(flow_id, str) and flow_id.strip():
                        return flow_id.strip()
            return path.stem
        return arg

    def _cmd_enqueue(args):
        try:
            payload = _load_json_arg(args.input, default={})
            headers = _load_json_arg(args.headers, default={}) if args.headers else {}
            trace = _load_json_arg(args.trace, default={}) if args.trace else {}
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)

        if args.idempotency_key:
            headers.setdefault("idempotency_key", args.idempotency_key)

        try:
            flow_id = _resolve_flow_id(args.flow)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)

        if not flow_id:
            print("Unable to determine flow id", file=sys.stderr)
            sys.exit(1)

        queue_backend = args.queue
        if queue_backend == "file":
            queue_dir = Path(args.queue_dir).resolve()
            queue_dir.mkdir(parents=True, exist_ok=True)
            queue = FileWorkQueue(str(queue_dir))
        else:
            queue = InMemoryWorkQueue()

        idem_dir = Path(args.idempotency_dir).resolve()
        idem_dir.mkdir(parents=True, exist_ok=True)
        idem_store = IdempotencyStore(dir_path=str(idem_dir))

        manager = TaskQueueManager(queue, idem_store)
        outcome = manager.enqueue(
            flow_id=flow_id,
            input=payload,
            headers=headers or None,
            trace=trace or None,
        )
        if queue_backend == "file":
            queue.flush()
            queue.close()

        if outcome.queued and outcome.envelope:
            print(f"enqueued task {outcome.envelope.task_id} for flow '{flow_id}'")
        elif outcome.cached_result is not None:
            print("duplicate request (served from idempotency cache)")
        else:
            print("task already pending; not enqueued")

    enqueue_parser.set_defaults(func=_cmd_enqueue)

    workers_parser = sub.add_parser(
        "workers",
        help="manage worker processes",
        description="Start, monitor, and gracefully stop worker pools.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:\n  tm workers start -n 4 --queue file --lease-ms 30000\n  tm workers stop""",
    )
    workers_sub = workers_parser.add_subparsers(dest="wcmd")
    workers_sub.required = True

    workers_start = workers_sub.add_parser(
        "start",
        help="start worker pool",
        description="Launch a pool of TraceMind workers and keep it running until signalled.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm workers start -n 4 --queue file --lease-ms 30000""",
    )
    workers_start.add_argument(
        "-n", "--num", dest="worker_count", type=int, default=1, help="number of worker processes"
    )
    workers_start.add_argument("--queue", choices=["file", "memory"], default="file", help="queue backend")
    workers_start.add_argument("--queue-dir", default="data/queue", help="queue directory (file backend)")
    workers_start.add_argument("--idempotency-dir", default="data/idempotency", help="idempotency cache directory")
    workers_start.add_argument("--dlq-dir", default="data/dlq", help="dead letter queue directory")
    workers_start.add_argument(
        "--runtime",
        default="tm.app.wiring_flows:_runtime",
        help="runtime factory in module:attr format",
    )
    workers_start.add_argument("--lease-ms", type=int, default=30_000, help="lease duration in milliseconds")
    workers_start.add_argument("--batch", type=int, default=1, help="tasks to lease per fetch")
    workers_start.add_argument("--poll", type=float, default=0.5, help="poll interval when idle (seconds)")
    workers_start.add_argument("--heartbeat", type=float, default=5.0, help="heartbeat interval (seconds)")
    workers_start.add_argument(
        "--heartbeat-timeout", type=float, default=15.0, help="heartbeat timeout before restart (seconds)"
    )
    workers_start.add_argument("--result-ttl", type=float, default=3600.0, help="idempotency result TTL (seconds)")
    workers_start.add_argument("--config", help="config file for retry policies", default="trace_config.toml")
    workers_start.add_argument("--drain-grace", type=float, default=10.0, help="grace period (s) when draining")
    workers_start.add_argument(
        "--pid-file",
        default="tm-workers.pid",
        help="write supervisor PID for tm workers stop",
    )

    def _cmd_workers_start(args):
        queue_dir = Path(args.queue_dir).resolve()
        queue_dir.mkdir(parents=True, exist_ok=True)
        idem_dir = Path(args.idempotency_dir).resolve()
        idem_dir.mkdir(parents=True, exist_ok=True)
        dlq_dir = Path(args.dlq_dir).resolve()
        dlq_dir.mkdir(parents=True, exist_ok=True)

        opts = WorkerOptions(
            worker_count=args.worker_count,
            queue_backend=args.queue,
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
        install_signal_handlers(supervisor)
        pid_path = Path(args.pid_file).resolve()
        try:
            pid_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            pid_path.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            print(f"warning: failed to write pid file at {pid_path}", file=sys.stderr)
        else:
            print(f"worker supervisor running (pid {os.getpid()}); ctrl-c or 'tm workers stop' to drain")
        try:
            supervisor.run_forever()
        finally:
            try:
                pid_path.unlink(missing_ok=True)
            except Exception:
                pass

    workers_start.set_defaults(func=_cmd_workers_start)

    workers_stop = workers_sub.add_parser(
        "stop",
        help="signal workers to drain",
        description="Send SIGTERM to the running worker supervisor so it drains and exits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm workers stop""",
    )
    workers_stop.add_argument(
        "--pid-file",
        default="tm-workers.pid",
        help="PID file written by 'tm workers start'",
    )
    workers_stop.add_argument(
        "--signal",
        choices=["TERM", "INT"],
        default="TERM",
        help="signal to send (default: TERM)",
    )

    def _cmd_workers_stop(args):
        pid_path = Path(args.pid_file).resolve()
        if not pid_path.exists():
            print(f"pid file not found at {pid_path}", file=sys.stderr)
            sys.exit(1)
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except Exception as exc:
            print(f"failed to read pid from {pid_path}: {exc}", file=sys.stderr)
            sys.exit(1)
        sig = signal.SIGTERM if args.signal == "TERM" else signal.SIGINT
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            print(f"no process with pid {pid}")
            try:
                pid_path.unlink(missing_ok=True)
            except Exception:
                pass
            return
        print(f"sent SIG{args.signal} to worker supervisor (pid {pid})")

    workers_stop.set_defaults(func=_cmd_workers_stop)

    queue_parser = sub.add_parser(
        "queue",
        help="queue utilities",
        description="Inspect queue state without poking running workers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm queue stats --queue file""",
    )
    queue_sub = queue_parser.add_subparsers(dest="qcmd")
    queue_sub.required = True

    queue_stats = queue_sub.add_parser(
        "stats",
        help="show queue metrics",
        description="Inspect queue depth, inflight tasks, and lag without leasing new work.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm queue stats --queue file""",
    )
    queue_stats.add_argument("--queue", choices=["file", "memory"], default="file", help="queue backend")
    queue_stats.add_argument("--queue-dir", default="data/queue", help="queue directory (file backend)")
    queue_stats.add_argument("--json", action="store_true", help="emit JSON instead of text")

    def _cmd_queue_stats(args):
        now = time.monotonic()
        if args.queue == "file":
            queue_dir = Path(args.queue_dir).resolve()
            queue_dir.mkdir(parents=True, exist_ok=True)
            queue = FileWorkQueue(str(queue_dir))
        else:
            queue = InMemoryWorkQueue()
        try:
            depth = queue.pending_count()
            oldest = queue.oldest_available_at()
            lag = max(0.0, now - oldest) if oldest is not None else 0.0
            entries = getattr(queue, "_entries", {})
            inflight = 0
            if isinstance(entries, Mapping):
                inflight = sum(1 for entry in entries.values() if getattr(entry, "token", None))
            ready = max(0, depth - inflight)
            stats = {
                "backend": args.queue,
                "depth": depth,
                "ready": ready,
                "inflight": inflight,
                "lag_seconds": lag,
            }
            if args.json:
                print(json.dumps(stats, ensure_ascii=False, indent=2))
            else:
                print(f"backend       : {stats['backend']}")
                print(f"depth         : {stats['depth']}")
                print(f"ready         : {stats['ready']}")
                print(f"inflight      : {stats['inflight']}")
                print(f"lag_seconds   : {stats['lag_seconds']:.3f}")
        finally:
            if args.queue == "file":
                queue.close()

    queue_stats.set_defaults(func=_cmd_queue_stats)

    dlq_parser = sub.add_parser(
        "dlq",
        help="dead letter queue tools",
        description="Inspect, requeue, or purge entries in the DLQ.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:\n  tm dlq ls --limit 5\n  tm dlq requeue dlq-1700*""",
    )
    dlq_sub = dlq_parser.add_subparsers(dest="dlqcmd")
    dlq_sub.required = True

    dlq_ls = dlq_sub.add_parser(
        "ls",
        help="list DLQ entries",
        description="Print pending dead letter entries for inspection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm dlq ls --since 15m --limit 5""",
    )
    dlq_ls.add_argument("--dlq-dir", default="data/dlq", help="dead letter directory")
    dlq_ls.add_argument("--limit", type=int, default=20, help="maximum entries to display")
    dlq_ls.add_argument("--since", help="only include entries newer than duration (e.g. 10m, 1h)")

    def _cmd_dlq_ls(args):
        store = DeadLetterStore(args.dlq_dir)
        count = 0
        since_cutoff = None
        if args.since:
            try:
                since_cutoff = time.time() - _parse_duration(args.since).total_seconds()
            except Exception as exc:
                print(f"invalid --since value: {exc}", file=sys.stderr)
                sys.exit(1)
        for record in store.list():
            if since_cutoff is not None and record.timestamp < since_cutoff:
                continue
            print(
                json.dumps(
                    {
                        "entry_id": record.entry_id,
                        "flow_id": record.flow_id,
                        "attempt": record.attempt,
                        "timestamp": record.timestamp,
                        "error": record.error,
                    },
                    ensure_ascii=False,
                )
            )
            count += 1
            if args.limit and count >= args.limit:
                break

    dlq_ls.set_defaults(func=_cmd_dlq_ls)

    dlq_requeue = dlq_sub.add_parser(
        "requeue",
        help="requeue DLQ entries",
        description="Return one or more DLQ entries to the work queue.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm dlq requeue dlq-1700* --dlq-dir data/dlq""",
    )
    dlq_requeue.add_argument("pattern", help="Entry id or glob-style pattern")
    dlq_requeue.add_argument("--dlq-dir", default="data/dlq")
    dlq_requeue.add_argument("--queue-dir", default="data/queue")
    dlq_requeue.add_argument("--idempotency-dir", default="data/idempotency")
    dlq_requeue.add_argument("--config", default="trace_config.toml")
    dlq_requeue.add_argument("--all", action="store_true", help="requeue all matching entries")

    def _cmd_dlq_requeue(args):
        store = DeadLetterStore(args.dlq_dir)
        matches = [
            record
            for record in store.list()
            if record.entry_id == args.pattern or fnmatch.fnmatch(record.entry_id, args.pattern)
        ]
        if not matches:
            print(f"no DLQ entries match '{args.pattern}'", file=sys.stderr)
            sys.exit(1)
        if not args.all:
            matches = matches[:1]
        queue = FileWorkQueue(str(Path(args.queue_dir).resolve()))
        idem = IdempotencyStore(dir_path=str(Path(args.idempotency_dir).resolve()))
        policy = load_retry_policy(args.config)
        manager = TaskQueueManager(queue, idem, retry_policy=policy)
        try:
            for record in matches:
                headers = dict(record.task.get("headers", {})) if isinstance(record.task, Mapping) else {}
                trace = record.task.get("trace") if isinstance(record.task, Mapping) else {}
                outcome = manager.enqueue(
                    flow_id=record.flow_id,
                    input=record.task.get("input", {}),
                    headers=headers,
                    trace=trace if isinstance(trace, Mapping) else {},
                )
                if outcome.envelope:
                    print(f"requeued {record.entry_id} -> task {outcome.envelope.task_id}")
                else:
                    print(f"skipped {record.entry_id} (duplicate)")
                store.consume(record.entry_id, state="requeued")
        finally:
            queue.flush()
            queue.close()

    dlq_requeue.set_defaults(func=_cmd_dlq_requeue)

    dlq_purge = dlq_sub.add_parser(
        "purge",
        help="purge DLQ entries",
        description="Permanently archive matching DLQ entries after confirmation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:\n  tm dlq purge dlq-1700* --yes""",
    )
    dlq_purge.add_argument("pattern", help="Entry id or glob-style pattern")
    dlq_purge.add_argument("--dlq-dir", default="data/dlq")
    dlq_purge.add_argument("--yes", action="store_true", help="skip confirmation prompt")

    def _cmd_dlq_purge(args):
        store = DeadLetterStore(args.dlq_dir)
        matches = [
            record.entry_id
            for record in store.list()
            if record.entry_id == args.pattern or fnmatch.fnmatch(record.entry_id, args.pattern)
        ]
        if not matches:
            print(f"no DLQ entries match '{args.pattern}'", file=sys.stderr)
            sys.exit(1)
        if not args.yes:
            prompt = (
                f"Permanently purge {len(matches)} entr{'y' if len(matches)==1 else 'ies'}? type 'purge' to confirm: "
            )
            response = input(prompt)
            if response.strip().lower() != "purge":
                print("aborted")
                return
        for entry_id in matches:
            record = store.consume(entry_id, state="purged")
            if record is None:
                print(f"entry '{entry_id}' already handled")
            else:
                print(f"purged {entry_id}")

    dlq_purge.set_defaults(func=_cmd_dlq_purge)

    register_flow_commands(sub)
    register_validate_command(sub)
    register_simulate_command(sub)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        result = args.func(args)
        if isinstance(result, int):
            return result
    # return 0 even when no subcommand to mirror previous behavior
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
