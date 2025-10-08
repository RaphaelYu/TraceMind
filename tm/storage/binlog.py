# tm/storage/binlog.py
import os
import time
import zlib
from typing import BinaryIO, Iterable, Iterator, Optional, Tuple

MAGIC = b"TMG1"
VER = 1


def _varint_encode(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            break
    return bytes(out)


def _varint_decode(buf: memoryview, pos: int) -> Tuple[int, int]:
    shift, out = 0, 0
    while True:
        b = buf[pos]
        pos += 1
        out |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
    return out, pos


class BinaryLogWriter:
    def __init__(self, dir_path: str, seg_bytes: int = 128_000_000):
        self.dir = dir_path
        os.makedirs(self.dir, exist_ok=True)
        self.seg_bytes = seg_bytes
        self.fp: Optional[BinaryIO] = None
        self.path: Optional[str] = None
        self.size = 0
        self._open_new_segment()

    def _open_new_segment(self) -> None:
        ts = int(time.time())
        self.path = os.path.join(self.dir, f"events-{ts}.tmbl")
        self.fp = open(self.path, "ab", buffering=1024 * 1024)
        self.size = 0

    def append_many(self, records: Iterable[Tuple[str, bytes]]) -> None:
        # records: (etype, payload_bytes)
        if self.fp is None:
            raise RuntimeError("binary log writer is closed")
        chunks = []
        for etype, payload in records:
            etb = etype.encode("utf-8")
            body = _varint_encode(len(etb)) + etb + payload
            frame = MAGIC + bytes([VER]) + _varint_encode(len(body)) + body
            crc = zlib.crc32(frame) & 0xFFFFFFFF
            chunks.append(frame + crc.to_bytes(4, "big"))
        blob = b"".join(chunks)
        n = self.fp.write(blob)
        self.size += n
        if self.size >= self.seg_bytes:
            self.fp.flush()
            os.fsync(self.fp.fileno())
            self.fp.close()
            self._open_new_segment()

    def flush_fsync(self) -> None:
        if self.fp is None:
            return
        self.fp.flush()
        os.fsync(self.fp.fileno())

    def close(self) -> None:
        if self.fp is None:
            return
        self.fp.flush()
        os.fsync(self.fp.fileno())
        self.fp.close()
        self.fp = None


class BinaryLogReader:
    def __init__(self, dir_path: str):
        self.dir = dir_path

    def scan(self) -> Iterator[Tuple[str, bytes]]:
        for name in sorted(os.listdir(self.dir)):
            if not name.endswith(".tmbl"):
                continue
            with open(os.path.join(self.dir, name), "rb") as f:
                data = f.read()
                mv, p = memoryview(data), 0
                L = len(data)
                while p + 9 <= L:  # magic(4)+ver(1)+len(varint)+crc(4)
                    if mv[p : p + 4].tobytes() != MAGIC:
                        break
                    start = p
                    p += 4
                    _ = mv[p]
                    p += 1

                    blen, p = _varint_decode(mv, p)
                    if p + blen + 4 > L:
                        break
                    frame = mv[start : p + blen]  # include magic+ver+len for crc window
                    body = mv[p : p + blen].tobytes()
                    p += blen
                    crc = int.from_bytes(mv[p : p + 4], "big")
                    p += 4
                    if (zlib.crc32(frame.tobytes()) & 0xFFFFFFFF) != crc:
                        break
                    et_len, q = _varint_decode(memoryview(body), 0)
                    et = body[q : q + et_len].decode("utf-8")
                    payload = body[q + et_len :]
                    yield et, payload
