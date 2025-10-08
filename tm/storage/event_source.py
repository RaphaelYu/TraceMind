from typing import Iterator, Tuple

from .binlog import BinaryLogReader


class EventSource:
    """Uniform iterator over events stored in the binary log.
    Payloads are returned as raw bytes; the caller decides how to decode.
    """

    def __init__(self, log_dir: str):
        self._reader = BinaryLogReader(log_dir)

    def stream(self) -> Iterator[Tuple[str, bytes]]:
        return self._reader.scan()
