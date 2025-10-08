import asyncio
import time
import os
from typing import Any, Dict, List, Tuple
from fastapi import FastAPI, Response
from pydantic import BaseModel
import orjson

from tm.config import Config
from tm.core.bus import EventBus
from tm.core.service import AppService
from tm.core.commands import UpsertObject
from tm.io.sse import SSEHub
from tm.io.metrics import Metrics
from tm.storage.binlog import BinaryLogWriter
from tm.pipeline.engine import Pipeline
from tm.pipeline.trace_store import PipelineTraceSink
from tm.pipeline.selectors import match as sel_match
from tm.app.demo_plan import build_plan

cfg = Config()
app = FastAPI()

# in-proc components
bus = EventBus()
sse = SSEHub()
metrics = Metrics()

# ingestion queue and writer

Q: asyncio.Queue[Tuple[bytes, bytes]] = asyncio.Queue(maxsize=cfg.q_max)
writer = BinaryLogWriter(cfg.effective_log_dir(), seg_bytes=cfg.seg_bytes)


class InEvent(BaseModel):
    kind: str
    obj_id: str
    payload: Dict[str, Any]


# sink callable for AppService: put events into Q as (etype, payload_json_bytes)
def sink(events: List[object]) -> None:
    # Best-effort: enqueue without blocking in the request thread
    for e in events:
        if e.__class__.__name__ == "ObjectUpserted":
            payload = {"kind": e.kind, "obj_id": e.obj_id, "payload": e.payload, "txn_meta": e.txn_meta}
            item = (b"ObjectUpserted", orjson.dumps(payload))
            try:
                Q.put_nowait(item)
            except asyncio.QueueFull:
                # If full, fall back to slow path (await) via background task
                asyncio.create_task(Q.put(item))
            metrics.inc("ingested")


svc = AppService(sink=sink, bus=bus)

# --- Pipeline wiring (in-memory last snapshot) ---------------------------
_last: dict[str, dict] = {}
trace_sink = PipelineTraceSink(dir_path=os.path.join(cfg.data_dir, "trace"))
pipe = Pipeline(plan=build_plan(), trace_sink=trace_sink.append)

# naive JSON diff (dict/list/scalar)

Path = Tuple[Any, ...]


def _diff_json(old: Any, new: Any, path: Tuple[Any, ...] = ()) -> List[Tuple[Path, str, Any, Any]]:
    out: List[Tuple[Path, str, Any, Any]] = []
    if isinstance(old, type(new)):
        out.append((path, "modified", old, new))
        return out
    if isinstance(old, dict):
        keys = set(old) | set(new)
        for k in sorted(keys):
            if k not in old:
                out.append((path + (k,), "added", None, new[k]))
            elif k not in new:
                out.append((path + (k,), "removed", old[k], None))
            else:
                out.extend(_diff_json(old[k], new[k], path + (k,)))
    elif isinstance(old, list):
        n = max(len(old), len(new))
        for i in range(n):
            if i >= len(old):
                out.append((path + (i,), "added", None, new[i]))
            elif i >= len(new):
                out.append((path + (i,), "removed", old[i], None))
            else:
                out.extend(_diff_json(old[i], new[i], path + (i,)))
    else:
        if old != new:
            out.append((path, "modified", old, new))
    return out


# when events are published, run pipeline
def _on_event(ev: object):
    if ev.__class__.__name__ != "ObjectUpserted":
        return
    key = f"{ev.kind}:{ev.obj_id}"
    old = _last.get(key) or {}
    new = ev.payload or {}
    changes = _diff_json(old, new)
    changed_paths = [p for (p, _, __, ___) in changes]
    ctx = {"kind": ev.kind, "id": ev.obj_id, "old": old, "new": new, "effects": []}
    out = pipe.run(ctx, changed_paths, sel_match)
    _last[key] = out.get("new", new)


bus.subscribe(_on_event)


# background pump: micro-batch queue -> binlog
async def pump():
    buf: List[Tuple[str, bytes]] = []
    last = time.time()
    last_flush = last

    while True:
        try:
            et_b, pb = await asyncio.wait_for(Q.get(), timeout=cfg.batch_ms)
            buf.append((et_b.decode(), pb))
        except asyncio.TimeoutError:
            pass
        now = time.time()

        if buf and (len(buf) >= cfg.batch_max or (now - last) >= cfg.batch_ms):
            writer.append_many(buf)
            metrics.set_flush((time.time() - now) * 1000.0)
            buf.clear()
            last = now

        if (now - last_flush) >= cfg.fsync_ms:
            writer.flush_fsync()
            last_flush = now

        metrics.set_q(Q.qsize())
        # drain one SSE payload per loop to keep UI responsive
        sse.drain_once()


@app.on_event("startup")
async def on_start():
    asyncio.create_task(pump())


@app.post("/api/commands/upsert")
async def upsert(ev: InEvent):
    svc.handle(UpsertObject(ev.kind, ev.obj_id, ev.payload, {"from": "http"}))
    return {"ok": True}


@app.get("/metrics")
async def prom_metrics():
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")


@app.get("/stream")
async def sse_stream():
    # very tiny SSE endpoint using Starlette low-level interface
    from starlette.responses import StreamingResponse

    async def _gen():
        loop = asyncio.get_event_loop()
        q: asyncio.Queue[str] = asyncio.Queue()
        # bridge: attach a thread-unsafe writer using a pipe through this coroutine

        class _W:
            def write(self, b: bytes):
                loop.call_soon_threadsafe(q.put_nowait, b.decode())

            def flush(self):
                pass

        sse.attach(_W())
        try:
            while True:
                msg = await q.get()
                yield msg

        finally:
            sse.detach(_W())

    return StreamingResponse(_gen(), media_type="text/event-stream")
