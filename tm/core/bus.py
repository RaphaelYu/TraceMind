from typing import Callable, List


class EventBus:
    def __init__(self):
        self._subs: List[Callable[[object], None]] = []

    def subscribe(self, fn: Callable[[object], None]) -> None:
        self._subs.append(fn)

    def publish(self, ev: object) -> None:
        for fn in list(self._subs):
            try:
                fn(ev)

            except Exception:
                # best-effort in starter pack; add logging as needed
                pass
