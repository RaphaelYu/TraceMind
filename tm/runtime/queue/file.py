from __future__ import annotations

import json
import os
import re
import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence

try:  # pragma: no cover - platform specific
    import fcntl  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    fcntl = None  # type: ignore[attr-defined]

try:  # pragma: no cover - windows fallback
    import msvcrt  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    msvcrt = None  # type: ignore[attr-defined]

from .base import LeasedTask, WorkQueue

_SEGMENT_RE = re.compile(r"segment-(\d{6})\.log$")


@dataclass
class _FileEntry:
    task: Mapping[str, Any]
    segment_seq: int
    available_at: float
    lease_deadline: float = 0.0
    token: str | None = None
    acked: bool = False


@dataclass
class _FileSegment:
    seq: int
    path: str
    index_path: str
    start_offset: int
    end_offset: int
    size_bytes: int
    record_count: int
    pending: int
    acked: set[int] = field(default_factory=set)

    def add_record(self, offset: int, size: int) -> None:
        if self.record_count == 0:
            self.start_offset = offset
        self.end_offset = offset
        self.record_count += 1
        self.pending += 1
        self.size_bytes += size

    def ack(self, offset: int) -> None:
        if offset not in self.acked:
            self.acked.add(offset)
            if self.pending > 0:
                self.pending -= 1


def _lock_file(fh) -> None:
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    elif msvcrt is not None:
        fh.seek(0)
        # Lock a single byte as a coarse mutex
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)


def _unlock_file(fh) -> None:
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    elif msvcrt is not None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


class FileWorkQueue(WorkQueue):
    """File-backed segmented queue with leases and ack/nack support."""

    def __init__(
        self,
        dir_path: str,
        *,
        segment_max_bytes: int = 64 * 1024 * 1024,
        fsync_on_put: bool = False,
    ) -> None:
        self._dir = dir_path
        self._io_lock = threading.Lock()
        self._segment_max_bytes = max(segment_max_bytes, 1024)
        self._fsync_on_put = fsync_on_put
        os.makedirs(self._dir, exist_ok=True)
        self._lock = threading.Lock()
        self._segments: list[_FileSegment] = []
        self._segments_by_seq: Dict[int, _FileSegment] = {}
        self._entries: Dict[int, _FileEntry] = {}
        self._ready_heap: list[tuple[float, int]] = []
        self._ready_set: set[int] = set()
        self._lease_seq = 0
        self._next_offset = 0
        self._current_segment: _FileSegment | None = None
        self._meta_path = os.path.join(self._dir, "queue.meta")
        self._offset_path = os.path.join(self._dir, "queue.offset")
        max_seq, max_offset = self._load_existing_segments()
        self._initialize_meta(max_seq)
        self._initialize_offset(max_offset + 1 if max_offset >= 0 else 0)
        if self._current_segment is None:
            with self._io_lock:
                self._rotate_segment_unlocked()

    # ------------------------------------------------------------------
    # WorkQueue interface
    # ------------------------------------------------------------------
    def put(self, task: Mapping[str, Any]) -> int:
        payload: Mapping[str, Any]
        if isinstance(task, MutableMapping):
            payload = dict(task)
        else:
            payload = task
        with self._io_lock:
            self._ensure_active_segment()
            segment = self._current_segment
            if segment is None:
                raise RuntimeError("active segment missing after ensure")
            offset = self._allocate_offset()
            record = (
                json.dumps(
                    {
                        "offset": offset,
                        "task": payload,
                        "enqueued_at": time.time(),
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            if segment.size_bytes + len(record) > self._segment_max_bytes and segment.record_count > 0:
                self._rotate_segment_unlocked()
                segment = self._current_segment
                if segment is None:
                    raise RuntimeError("active segment missing after rotate")
            with open(segment.path, "ab") as fp:
                _lock_file(fp)
                try:
                    fp.write(record)
                    if self._fsync_on_put:
                        fp.flush()
                        os.fsync(fp.fileno())
                finally:
                    _unlock_file(fp)
            available_at = _extract_available_at(payload)
            with self._lock:
                segment.add_record(offset, len(record))
                entry = _FileEntry(task=payload, segment_seq=segment.seq, available_at=available_at)
                self._entries[offset] = entry
                self._push_ready(offset, available_at)
            self._maybe_rotate_unlocked()
        return offset

    def lease(self, count: int, lease_ms: int) -> Sequence[LeasedTask]:
        if count <= 0:
            return []
        lease_delta = max(lease_ms, 0) / 1000.0
        now = time.monotonic()
        leased: list[LeasedTask] = []
        with self._lock:
            self._release_expired(now)
            while len(leased) < count:
                item = self._pop_ready(now)
                if item is None:
                    break
                offset, available_at = item
                if offset is None:
                    break
                entry = self._entries.get(offset)
                if entry is None:
                    continue
                self._lease_seq += 1
                token = f"lease-{self._lease_seq}"
                entry.token = token
                entry.lease_deadline = now + lease_delta
                leased.append(
                    LeasedTask(
                        offset=offset,
                        task=entry.task,
                        lease_deadline=entry.lease_deadline,
                        token=token,
                    )
                )
        return leased

    def ack(self, offset: int, token: str) -> None:
        with self._lock:
            entry = self._entries.get(offset)
            if entry is None:
                return
            if entry.token != token:
                return
            segment = self._segments_by_seq.get(entry.segment_seq)
            if segment is None:
                return
            segment.ack(offset)
            entry.token = None
            entry.lease_deadline = 0.0
            self._entries.pop(offset, None)
            self._persist_segment_state(segment)
            self._maybe_compact_head()

    def nack(self, offset: int, token: str, *, requeue: bool = True) -> None:
        with self._lock:
            entry = self._entries.get(offset)
            if entry is None:
                return
            if entry.token != token:
                return
            entry.token = None
            entry.lease_deadline = 0.0
            if requeue:
                available_at = entry.available_at
                now = time.monotonic()
                if available_at < now:
                    available_at = now
                    entry.available_at = available_at
                self._push_ready(offset, available_at)
            else:
                segment = self._segments_by_seq.get(entry.segment_seq)
                if segment is None:
                    return
                segment.ack(offset)
                self._entries.pop(offset, None)
                self._persist_segment_state(segment)
                self._maybe_compact_head()

    def reschedule(self, offset: int, *, available_at: float) -> None:
        with self._lock:
            entry = self._entries.get(offset)
            if entry is None:
                return
            entry.available_at = available_at
            if entry.token is None:
                self._push_ready(offset, available_at)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def oldest_available_at(self) -> Optional[float]:
        with self._lock:
            candidates = [entry.available_at for entry in self._entries.values() if entry.token is None]
        if not candidates:
            return None
        return min(candidates)

    def flush(self) -> None:
        return

    def close(self) -> None:
        return

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_existing_segments(self) -> tuple[int, int]:
        max_seq = 0
        max_offset = -1
        for name in sorted(os.listdir(self._dir)):
            match = _SEGMENT_RE.match(name)
            if not match:
                continue
            seq = int(match.group(1))
            path = os.path.join(self._dir, name)
            index_path = os.path.join(self._dir, f"segment-{seq:06d}.idx")
            segment = self._build_segment_from_files(seq, path, index_path)
            self._segments.append(segment)
            self._segments_by_seq[seq] = segment
            max_seq = max(max_seq, seq)
            if segment.end_offset > max_offset:
                max_offset = segment.end_offset
        if max_offset >= 0:
            self._next_offset = max_offset + 1
        if self._segments:
            last = self._segments[-1]
            self._open_segment_file(last, append=True)
        return max_seq, max_offset

    def _build_segment_from_files(self, seq: int, path: str, index_path: str) -> _FileSegment:
        acked: set[int] = set()
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                ack_list = raw.get("acked", [])
                acked = {int(v) for v in ack_list}
            except Exception:
                acked = set()
        start_offset = self._next_offset
        end_offset = self._next_offset - 1
        record_count = 0
        pending = 0
        size_bytes = 0
        try:
            with open(path, "rb") as fh:
                for line in fh:
                    if not line.strip():
                        size_bytes += len(line)
                        continue
                    size_bytes += len(line)
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    offset = int(data["offset"])
                    if record_count == 0:
                        start_offset = offset
                    end_offset = offset
                    record_count += 1
                    raw_task = data.get("task")
                    task_payload: Mapping[str, Any]
                    if isinstance(raw_task, Mapping):
                        task_payload = raw_task
                    else:
                        task_payload = {}
                    if offset not in acked:
                        pending += 1
                        available_at = _extract_available_at(task_payload)
                        self._entries[offset] = _FileEntry(
                            task=task_payload,
                            segment_seq=seq,
                            available_at=available_at,
                        )
                        self._push_ready(offset, available_at)
        except FileNotFoundError:
            pass
        return _FileSegment(
            seq=seq,
            path=path,
            index_path=index_path,
            start_offset=start_offset if record_count else self._next_offset,
            end_offset=end_offset,
            size_bytes=size_bytes,
            record_count=record_count,
            pending=pending,
            acked=acked,
        )

    def _ensure_active_segment(self) -> None:
        if self._current_segment is None:
            self._rotate_segment_unlocked()

    def _maybe_rotate_unlocked(self) -> None:
        segment = self._current_segment
        if segment is None:
            return
        if segment.size_bytes >= self._segment_max_bytes:
            self._rotate_segment_unlocked()

    def _rotate_segment_unlocked(self) -> None:
        seq = self._allocate_segment_seq()
        name = f"segment-{seq:06d}.log"
        path = os.path.join(self._dir, name)
        index_path = os.path.join(self._dir, f"segment-{seq:06d}.idx")
        segment = _FileSegment(
            seq=seq,
            path=path,
            index_path=index_path,
            start_offset=self._next_offset,
            end_offset=self._next_offset - 1,
            size_bytes=0,
            record_count=0,
            pending=0,
        )
        self._segments.append(segment)
        self._segments_by_seq[seq] = segment
        self._open_segment_file(segment, append=False)

    def _open_segment_file(self, segment: _FileSegment, *, append: bool) -> None:
        mode = "ab" if append or os.path.exists(segment.path) else "wb"
        with open(segment.path, mode) as fp:
            fp.seek(0, os.SEEK_END)
            segment.size_bytes = fp.tell()
        self._current_segment = segment

    def _initialize_meta(self, max_seq: int) -> None:
        path = self._meta_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a+b") as fh:
            _lock_file(fh)
            try:
                fh.seek(0)
                data = fh.read().decode("utf-8").strip()
                current = int(data) if data else 0
                if current < max_seq:
                    fh.seek(0)
                    fh.write(str(max_seq).encode("utf-8"))
                    fh.truncate()
            finally:
                _unlock_file(fh)

    def _initialize_offset(self, initial_value: int) -> None:
        path = self._offset_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a+b") as fh:
            _lock_file(fh)
            try:
                fh.seek(0)
                data = fh.read().decode("utf-8").strip()
                current = int(data) if data else 0
                if current < initial_value:
                    fh.seek(0)
                    fh.write(str(initial_value).encode("utf-8"))
                    fh.truncate()
                else:
                    initial_value = current
            finally:
                _unlock_file(fh)
        self._next_offset = initial_value

    def _allocate_segment_seq(self) -> int:
        path = self._meta_path
        with open(path, "r+b") as fh:
            _lock_file(fh)
            try:
                fh.seek(0)
                data = fh.read().decode("utf-8").strip()
                current = int(data) if data else 0
                current += 1
                fh.seek(0)
                fh.write(str(current).encode("utf-8"))
                fh.truncate()
                return current
            finally:
                _unlock_file(fh)

    def _allocate_offset(self) -> int:
        path = self._offset_path
        with open(path, "r+b") as fh:
            _lock_file(fh)
            try:
                fh.seek(0)
                data = fh.read().decode("utf-8").strip()
                current = int(data) if data else 0
                next_value = current + 1
                fh.seek(0)
                fh.write(str(next_value).encode("utf-8"))
                fh.truncate()
                self._next_offset = next_value
                return current
            finally:
                _unlock_file(fh)

    def _push_ready(self, offset: int, available_at: float) -> None:
        if offset in self._ready_set:
            return
        heapq.heappush(self._ready_heap, (available_at, offset))
        self._ready_set.add(offset)

    def _pop_ready(self, now: float) -> tuple[int, float] | None:
        while self._ready_heap:
            available_at, offset = heapq.heappop(self._ready_heap)
            self._ready_set.discard(offset)
            if available_at > now:
                heapq.heappush(self._ready_heap, (available_at, offset))
                self._ready_set.add(offset)
                return None
            entry = self._entries.get(offset)
            if entry is None or entry.token is not None:
                continue
            return offset, available_at
        return None

    def _release_expired(self, now: float) -> None:
        for offset, entry in list(self._entries.items()):
            if entry.token is None or entry.acked:
                continue
            if entry.lease_deadline <= now:
                entry.token = None
                entry.lease_deadline = 0.0
                self._push_ready(offset, entry.available_at)

    def _persist_segment_state(self, segment: _FileSegment) -> None:
        tmp_path = segment.index_path + ".tmp"
        data = {
            "acked": sorted(segment.acked),
            "start_offset": segment.start_offset,
            "end_offset": segment.end_offset,
            "record_count": segment.record_count,
        }
        lock_fp = None
        try:
            if fcntl is not None:
                lock_fp = open(segment.index_path, "a+b")
                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, separators=(",", ":"))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, segment.index_path)
        finally:
            if lock_fp is not None:
                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
                lock_fp.close()

    def _maybe_compact_head(self) -> None:
        with self._io_lock:
            while self._segments:
                head = self._segments[0]
                if head.pending > 0:
                    break
                if self._current_segment is not None and head.seq == self._current_segment.seq:
                    break
                try:
                    os.remove(head.path)
                except FileNotFoundError:
                    pass
                try:
                    os.remove(head.index_path)
                except FileNotFoundError:
                    pass
                self._segments.pop(0)
                self._segments_by_seq.pop(head.seq, None)


def _extract_available_at(task: Mapping[str, Any]) -> float:
    try:
        scheduled = float(task.get("scheduled_at", 0.0))
    except Exception:
        scheduled = 0.0
    now_wall = time.time()
    now_monotonic = time.monotonic()
    if scheduled <= 0:
        return now_monotonic
    delay = max(0.0, scheduled - now_wall)
    return now_monotonic + delay
