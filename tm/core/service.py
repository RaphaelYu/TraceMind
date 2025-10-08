from typing import List
from .commands import UpsertObject, Command
from .events import ObjectUpserted, Event


class AppService:
    """Accept commands, convert to events, append to store via a provided sink,
    then publish on the in-proc event bus. The store sink here is a callable
    that accepts a list of events and is expected to handle persistence (micro-batch queue)."""

    def __init__(self, sink, bus):
        self._sink = sink  # sink(events: List[Event]) -> None
        self._bus = bus

    def handle(self, cmd: Command) -> List[Event]:
        evs: List[Event] = []

        if isinstance(cmd, UpsertObject):
            evs.append(ObjectUpserted(cmd.kind, cmd.obj_id, cmd.payload, cmd.txn_meta))
        else:
            raise NotImplementedError(type(cmd))

        # push to persistence sink (async micro-batch behind the scenes)
        self._sink(evs)
        # publish to local subscribers (UI, metrics, etc.)

        for e in evs:
            self._bus.publish(e)

        return evs
