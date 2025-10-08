from collections import Counter


class Metrics:
    def __init__(self):
        self.c = Counter()
        self.q_size = 0
        self.last_flush_ms = 0.0

    def inc(self, key: str, n: int = 1):
        self.c[key] += n

    def set_q(self, n: int):
        self.q_size = n

    def set_flush(self, ms: float):
        self.last_flush_ms = ms

    def render(self) -> str:
        lines = []

        for k, v in self.c.items():
            lines.append(f"# TYPE {k} counter\n{k} {v}")

        lines.append(f"# TYPE queue_size gauge\nqueue_size {self.q_size}")
        lines.append(f"# TYPE last_flush_ms gauge\nlast_flush_ms {self.last_flush_ms}")

        return "\n".join(lines) + "\n"
