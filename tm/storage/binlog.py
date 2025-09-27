# tm/storage/binlog.py
import os, time, zlib
from typing import Iterable, Iterator, Tuple

MAGIC = b"TMG1"
VER   = 1

def _varint_encode(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n: break
    return bytes(out)

def _varint_decode(buf: memoryview, pos: int) -> Tuple[int,int]:
    shift = 0; out = 0
    while True:
        b = buf[pos]; pos += 1
        out |= (b & 0x7F) << shift
        if (b & 0x80) == 0: break
        shift += 7
    return out, pos

class BinaryLogWriter:
    def __init__(self, dir_path: str, seg_bytes: int = 128_000_000):
        self.dir = dir_path; os.makedirs(self.dir, exist_ok=True)
        self.seg_bytes = seg_bytes
        self.fp = None; self.path = None; self.size = 0
        self._open_new_segment()

    def _open_new_segment(self):
        ts = int(time.time())
        self.path = os.path.join(self.dir, f"events-{ts}.tmbl")
        self.fp = open(self.path, "ab", buffering=1024*1024)
        self.size = 0

    def append_many(self, records: Iterable[Tuple[str, bytes]]):
        # records: (etype, payload_bytes)
        chunks = []
        for etype, payload in records:
            etb = etype.encode("utf-8")
            body = _varint_encode(len(etb)) + etb + payload
            frame = MAGIC + bytes([VER]) + _varint_encode(len(body)) + body
            crc = zlib.crc32(frame) & 0xffffffff
            chunks.append(frame + crc.to_bytes(4, "big"))
        blob = b"".join(chunks)
        n = self.fp.write(blob); self.size += n
        if self.size >= self.seg_bytes:
            self.fp.flush(); os.fsync(self.fp.fileno()); self.fp.close()
            self._open_new_segment()

    def flush_fsync(self):
        self.fp.flush(); os.fsync(self.fp.fileno())

    def close(self):
        if self.fp is None: return
        self.fp.flush(); os.fsync(self.fp.fileno()); self.fp.close()
        self.fp = None

class BinaryLogReader:
    def __init__(self, dir_path: str):
        self.dir = dir_path

    def scan(self) -> Iterator[Tuple[str, bytes]]:
        for name in sorted(os.listdir(self.dir)):
            if not name.endswith(".tmbl"): continue
            with open(os.path.join(self.dir, name), "rb") as f:
                data = f.read(); mv = memoryview(data); p = 0
                L = len(data)
                while p + 9 <= L:  # magic(4)+ver(1)+len(varint)+crc(4)
                    if mv[p:p+4].tobytes() != MAGIC: break
                    start = p
                    p += 4; ver = mv[p]; p += 1
                    len_pos = p
                    blen, p = _varint_decode(mv, p)
                    var_len = p - len_pos
                    if p + blen + 4 > L: break
                    frame = mv[start : p+blen]  # include magic+ver+len for crc window
                    body = mv[p : p+blen].tobytes()
                    p += blen
                    crc = int.from_bytes(mv[p:p+4], "big"); p += 4
                    if (zlib.crc32(frame.tobytes()) & 0xffffffff) != crc: break
                    et_len, q = _varint_decode(memoryview(body), 0)
                    et = body[q:q+et_len].decode("utf-8")
                    payload = body[q+et_len:]
                    yield et, payload
