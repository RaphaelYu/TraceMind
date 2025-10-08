import queue
import json


class SSEHub:
    def __init__(self):
        self._clients = set()
        self._q = queue.Queue()

    def publish(self, msg: dict) -> None:
        self._q.put(json.dumps(msg, ensure_ascii=False))

    def attach(self, wfile):
        self._clients.add(wfile)

    def detach(self, wfile):
        self._clients.discard(wfile)

    def drain_once(self):
        try:
            data = self._q.get_nowait()
        except queue.Empty:
            return

        dead = []
        for w in list(self._clients):
            try:
                w.write(f"data: {data}\n\n".encode())
                w.flush()
            except Exception:
                dead.append(w)

        for w in dead:
            self.detach(w)
