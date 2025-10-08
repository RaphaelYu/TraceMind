import json
import os
import tempfile
from itertools import count

import pytest

from tm.storage.binlog import BinaryLogReader, BinaryLogWriter


def test_binlog_writer_rolls_segments_and_reader_streams_records(monkeypatch: pytest.MonkeyPatch):
    clock = (t for t in count(start=1))
    monkeypatch.setattr("tm.storage.binlog.time.time", lambda: next(clock))

    with tempfile.TemporaryDirectory() as tmp:
        writer = BinaryLogWriter(tmp, seg_bytes=1)
        frames = [("TypeA", json.dumps({"idx": i}).encode()) for i in range(20)]

        writer.append_many(frames[:10])
        writer.append_many(frames[10:])
        writer.flush_fsync()
        writer.fp.close()

        segments = sorted(name for name in os.listdir(tmp) if name.endswith(".tmbl"))
        assert len(segments) >= 2

        reader = BinaryLogReader(tmp)
        out = list(reader.scan())

        assert [(etype, payload) for etype, payload in out] == [("TypeA", frame[1]) for frame in frames]
