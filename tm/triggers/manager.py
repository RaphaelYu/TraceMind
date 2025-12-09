from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import ssl
import socket
import time
import urllib.parse
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Dict, Iterable, Mapping, MutableMapping
from uuid import uuid4

from .config import (
    CronTriggerConfig,
    FileSystemTriggerConfig,
    TriggerBaseConfig,
    TriggerConfigSet,
    WebhookTriggerConfig,
)

LOGGER = logging.getLogger("tm.triggers.manager")


@dataclass(frozen=True)
class TriggerEvent:
    trigger_id: str
    kind: str
    flow_id: str
    payload: Mapping[str, object]
    headers: Mapping[str, str]
    idempotency_key: str | None = None


TriggerEventHandler = Callable[[TriggerEvent], Awaitable[None]]
AdapterBuilder = Callable[[TriggerConfigSet, TriggerEventHandler], Iterable["_BaseAdapter"]]


_ADAPTER_BUILDERS: list[AdapterBuilder] = []


def register_trigger_adapter(builder: AdapterBuilder) -> None:
    if builder not in _ADAPTER_BUILDERS:
        _ADAPTER_BUILDERS.append(builder)


class TriggerManager:
    """Orchestrates trigger adapters and dispatches events via a handler."""

    def __init__(self, config: TriggerConfigSet, handler: TriggerEventHandler) -> None:
        self._config = config
        self._handler = handler
        self._tasks: list[asyncio.Task[None]] = []

    async def run(self, stop_event: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        adapters: list[_BaseAdapter] = []
        for builder in _ADAPTER_BUILDERS:
            adapters.extend(builder(self._config, self._handler))

        self._tasks = [loop.create_task(adapter.run(stop_event)) for adapter in adapters]
        try:
            await stop_event.wait()
        finally:
            for task in self._tasks:
                task.cancel()
            for task in self._tasks:
                with suppress(asyncio.CancelledError):
                    await task
            self._tasks.clear()


class _BaseAdapter:
    async def run(self, stop_event: asyncio.Event) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class _CronAdapter(_BaseAdapter):
    def __init__(
        self,
        config: CronTriggerConfig,
        schedule: "CronSchedule",
        handler: TriggerEventHandler,
    ) -> None:
        self._config = config
        self._schedule = schedule
        self._handler = handler

    async def run(self, stop_event: asyncio.Event) -> None:
        next_fire = self._schedule.next_after(datetime.now())
        while not stop_event.is_set():
            delay = (next_fire - datetime.now()).total_seconds()
            if delay > 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    break
                except asyncio.TimeoutError:
                    pass
            context = {
                "scheduled_at": next_fire.isoformat(),
            }
            headers = {"trigger_scheduled_at": context["scheduled_at"]}
            event = _build_event(self._config, context, extra_headers=headers)
            try:
                await self._handler(event)
            except Exception:  # pragma: no cover - defensive
                LOGGER.exception("trigger handler failed for %s", self._config.id)
            next_fire = self._schedule.next_after(next_fire + timedelta(seconds=1))


def _build_event(
    config: TriggerBaseConfig,
    base_context: Mapping[str, object],
    *,
    extra_headers: Mapping[str, str] | None = None,
) -> TriggerEvent:
    context: Dict[str, object] = {
        "trigger_id": config.id,
        "trigger_kind": config.kind,
        "flow_id": config.flow_id,
        "event_id": uuid4().hex,
        "timestamp": time.time(),
    }
    context.update(base_context)
    payload = _render_template(config.input_template, context)
    payload.setdefault(
        "_trigger",
        {
            "id": config.id,
            "kind": config.kind,
            "event_id": context["event_id"],
            "timestamp": context["timestamp"],
        },
    )
    headers: dict[str, str] = {
        "trigger_id": str(config.id),
        "trigger_kind": str(config.kind),
        "trigger_event": str(context["event_id"]),
    }
    if extra_headers:
        headers.update(extra_headers)
    return TriggerEvent(
        trigger_id=config.id,
        kind=config.kind,
        flow_id=config.flow_id,
        payload=payload,
        headers=dict(headers),
        idempotency_key=config.idempotency_key,
    )


def _render_template(template: Mapping[str, object], context: Mapping[str, object]) -> Dict[str, object]:
    return {key: _render_value(value, context) for key, value in template.items()}


def _render_value(value: object, context: Mapping[str, object]) -> object:
    if isinstance(value, str):
        return _substitute_placeholders(value, context)
    if isinstance(value, Mapping):
        return {k: _render_value(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_value(v, context) for v in value]
    if isinstance(value, tuple):
        return tuple(_render_value(v, context) for v in value)
    return value


def _substitute_placeholders(template: str, context: Mapping[str, object]) -> str:
    result = template
    for key, raw_value in context.items():
        placeholders = ["{{ " + key + " }}", "{{" + key + "}}"]
        for placeholder in placeholders:
            if placeholder in result:
                result = result.replace(placeholder, str(raw_value))
    return result


class CronSchedule:
    def __init__(self, *, interval: float | None, fields: tuple[Iterable[int], ...]) -> None:
        self._interval = interval
        self._minute, self._hour, self._day, self._month, self._weekday = fields

    @staticmethod
    def from_expr(expr: str, timezone: str) -> "CronSchedule":
        expr = expr.strip()
        if expr.startswith("@every"):
            parts = expr.split()
            if len(parts) != 2:
                raise ValueError("@every expression must be '@every <seconds>'")
            interval = float(parts[1].rstrip("s"))
            if interval <= 0:
                raise ValueError("@every interval must be positive")
            return CronSchedule(interval=interval, fields=((), (), (), (), ()))

        fields = expr.split()
        if len(fields) != 5:
            raise ValueError("cron expression must have 5 fields")
        minute = _parse_cron_field(fields[0], 0, 59)
        hour = _parse_cron_field(fields[1], 0, 23)
        day = _parse_cron_field(fields[2], 1, 31)
        month = _parse_cron_field(fields[3], 1, 12)
        weekday = _parse_cron_field(fields[4], 0, 6)
        return CronSchedule(interval=None, fields=(minute, hour, day, month, weekday))

    def next_after(self, moment: datetime) -> datetime:
        if self._interval is not None:
            return moment + timedelta(seconds=self._interval)

        candidate = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(525600):  # up to one year lookahead
            if (
                candidate.minute in self._minute
                and candidate.hour in self._hour
                and candidate.month in self._month
                and _match_dom_dow(candidate, self._day, self._weekday)
            ):
                return candidate
            candidate += timedelta(minutes=1)
        raise RuntimeError("cron schedule could not find next occurrence within a year")


def _parse_cron_field(field: str, minimum: int, maximum: int) -> tuple[int, ...]:
    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if token == "*":
            values.update(range(minimum, maximum + 1))
            continue
        if token.startswith("*/"):
            step = int(token[2:])
            values.update(range(minimum, maximum + 1, step))
            continue
        if "/" in token:
            range_part, step_part = token.split("/", 1)
            step = int(step_part)
        else:
            range_part = token
            step = 1
        if "-" in range_part:
            start_str, end_str = range_part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
        else:
            start = end = int(range_part)
        for value in range(start, end + 1, step):
            if minimum <= value <= maximum:
                values.add(value)
    return tuple(sorted(values))


def _match_dom_dow(moment: datetime, days: Iterable[int], weekdays: Iterable[int]) -> bool:
    dom_match = moment.day in days if days else True
    dow = (moment.weekday() + 1) % 7  # convert Monday=0 -> Sunday=0 cron style
    dow_match = dow in weekdays if weekdays else True
    if days and weekdays:
        return dom_match or dow_match
    return dom_match and dow_match


def _build_webhook_servers(
    configs: Iterable[WebhookTriggerConfig],
    handler: TriggerEventHandler,
) -> list[_BaseAdapter]:
    groups: Dict[tuple[str, int, bool], list[WebhookTriggerConfig]] = {}
    for cfg in configs:
        use_tls = bool(cfg.tls_certfile and cfg.tls_keyfile)
        if not use_tls and not cfg.allow_cleartext:
            raise ValueError(f"webhook trigger '{cfg.id}' disallows cleartext but no TLS cert/key provided")
        key = (cfg.bind_host, cfg.bind_port, use_tls)
        groups.setdefault(key, []).append(cfg)

    servers: list[_BaseAdapter] = []
    for (host, port, use_tls), cfgs in groups.items():
        ssl_context = None
        if use_tls:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            certfile = cfgs[0].tls_certfile
            keyfile = cfgs[0].tls_keyfile
            if certfile is None or keyfile is None:
                raise ValueError("TLS enabled but certfile/keyfile not provided")
            ssl_context.load_cert_chain(certfile, keyfile)
        servers.append(_WebhookServer(host, port, ssl_context, cfgs, handler))
    return servers


class _WebhookServer(_BaseAdapter):
    MAX_BODY = 1_048_576  # 1 MB
    MAX_HEADERS = 64

    def __init__(
        self,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext | None,
        configs: Iterable[WebhookTriggerConfig],
        handler: TriggerEventHandler,
    ) -> None:
        self._host = host
        self._port = port
        self._ssl_context = ssl_context
        self._handler = handler
        self._routes: Dict[tuple[str, str], WebhookTriggerConfig] = {}
        for cfg in configs:
            key = (cfg.method.upper(), cfg.route)
            if key in self._routes:
                raise ValueError(f"duplicate webhook route {cfg.method} {cfg.route}")
            self._routes[key] = cfg
        self._server: asyncio.AbstractServer | None = None

    async def run(self, stop_event: asyncio.Event) -> None:
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._host,
            port=self._port,
            ssl=self._ssl_context,
        )
        sockets: list[socket.socket] = list(self._server.sockets or [])
        if sockets:
            bound = sockets[0].getsockname()
            LOGGER.info("webhook listening on %s:%s", bound[0], bound[1])
        try:
            async with self._server:
                await stop_event.wait()
        finally:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await _readline(reader)
            if not request_line:
                await _respond(writer, 400, "empty request")
                return
            parts = request_line.split()
            if len(parts) != 3:
                await _respond(writer, 400, "malformed request line")
                return
            method, target, _version = parts[0].upper(), parts[1], parts[2]
            headers = await _read_headers(reader, self.MAX_HEADERS)
            if headers is None:
                await _respond(writer, 400, "malformed headers")
                return
            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                await _respond(writer, 400, "invalid content-length")
                return
            if content_length < 0 or content_length > self.MAX_BODY:
                await _respond(writer, 413, "payload too large")
                return
            body = b""
            if content_length:
                body = await reader.readexactly(content_length)

            path, _, query = target.partition("?")
            cfg = self._routes.get((method, path))
            if cfg is None:
                await _respond(writer, 404, "route not found")
                return
            secret_header = headers.get("x-tracemind-secret")
            if cfg.secret and secret_header != cfg.secret:
                await _respond(writer, 401, "unauthorized")
                return

            body_text = body.decode("utf-8", errors="replace")
            parsed_body: object = body_text
            if headers.get("content-type", "").startswith("application/json") and body_text:
                with suppress(json.JSONDecodeError):
                    parsed_body = json.loads(body_text)

            query_params = urllib.parse.parse_qs(query, keep_blank_values=True)
            simple_query = {k: v if len(v) > 1 else v[0] for k, v in query_params.items()}

            context = {
                "method": method,
                "path": path,
                "query": simple_query,
                "headers": headers,
                "body": parsed_body,
                "body_text": body_text,
            }
            headers_extra = {
                "trigger_http_method": method,
                "trigger_http_path": path,
            }
            event = _build_event(cfg, context, extra_headers=headers_extra)
            await self._handler(event)
            await _respond(writer, 202, "accepted")
        except Exception:  # pragma: no cover - defensive cleanup
            LOGGER.exception("webhook handler error")
            await _respond(writer, 500, "internal error")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # pragma: no cover
                pass


async def _readline(reader: asyncio.StreamReader) -> str:
    line = await reader.readline()
    return line.decode("utf-8", errors="replace").strip()


async def _read_headers(reader: asyncio.StreamReader, limit: int) -> Dict[str, str] | None:
    headers: Dict[str, str] = {}
    for _ in range(limit):
        raw = await reader.readline()
        if raw in (b"\r\n", b"\n", b""):
            return headers
        decoded = raw.decode("utf-8", errors="replace")
        if ":" not in decoded:
            return None
        name, value = decoded.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return None


async def _respond(writer: asyncio.StreamWriter, status: int, message: str) -> None:
    reason = {
        200: "OK",
        202: "Accepted",
        400: "Bad Request",
        401: "Unauthorized",
        404: "Not Found",
        413: "Payload Too Large",
        500: "Internal Server Error",
    }.get(status, "OK")
    body = message.encode("utf-8")
    response = (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8") + body
    writer.write(response)
    with suppress(Exception):
        await writer.drain()


class _FileSystemWatcher(_BaseAdapter):
    def __init__(self, config: FileSystemTriggerConfig, handler: TriggerEventHandler) -> None:
        self._config = config
        self._handler = handler
        self._interval = max(0.5, float(config.interval_seconds))
        self._state: MutableMapping[str, float] = {}

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self._scan_once()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue

    async def _scan_once(self) -> None:
        root = Path(self._config.path)
        if not root.exists():
            return
        candidates = self._iter_files(root)
        now_state: MutableMapping[str, float] = {}
        for path in candidates:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            mtime = stat.st_mtime
            key = str(path)
            now_state[key] = mtime
            prev = self._state.get(key)
            if prev is None or mtime > prev:
                context = {
                    "path": str(path),
                    "name": path.name,
                    "parent": str(path.parent),
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(mtime).isoformat(),
                }
                headers = {"trigger_fs_path": str(path)}
                event = _build_event(self._config, context, extra_headers=headers)
                try:
                    await self._handler(event)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.exception("filesystem trigger failed for %s", self._config.id)
        self._state = now_state

    def _iter_files(self, root: Path) -> Iterable[Path]:
        pattern = self._config.pattern
        if self._config.recursive:
            for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
                for name in filenames:
                    if fnmatch.fnmatch(name, pattern):
                        yield Path(dirpath) / name
        else:
            try:
                for entry in os.scandir(root):
                    if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                        yield Path(entry.path)
            except FileNotFoundError:
                return


def _cron_builder(config: TriggerConfigSet, handler: TriggerEventHandler) -> Iterable[_BaseAdapter]:
    adapters: list[_BaseAdapter] = []
    for cron_cfg in config.cron:
        schedule = CronSchedule.from_expr(cron_cfg.cron, timezone=cron_cfg.timezone)
        adapters.append(_CronAdapter(cron_cfg, schedule, handler))
    return adapters


def _webhook_builder(config: TriggerConfigSet, handler: TriggerEventHandler) -> Iterable[_BaseAdapter]:
    if not config.webhook:
        return []
    return _build_webhook_servers(config.webhook, handler)


def _filesystem_builder(config: TriggerConfigSet, handler: TriggerEventHandler) -> Iterable[_BaseAdapter]:
    adapters: list[_BaseAdapter] = []
    for fs_cfg in config.filesystem:
        adapters.append(_FileSystemWatcher(fs_cfg, handler))
    return adapters


register_trigger_adapter(_cron_builder)
register_trigger_adapter(_webhook_builder)
register_trigger_adapter(_filesystem_builder)
