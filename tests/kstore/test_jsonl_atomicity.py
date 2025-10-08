import json
import threading

from tm.kstore.jsonl import JsonlKStore


def test_jsonl_atomicity(tmp_path):
    path = tmp_path / "state.jsonl"
    store = JsonlKStore(path)
    try:

        def _writer(idx: int) -> None:
            store.put(f"k:{idx}", {"value": idx})

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        items = list(store.scan("k:"))
        assert len(items) == 10

        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
        assert len(lines) == 10
        for line in lines:
            json.loads(line)

        leftovers = list(tmp_path.glob(".state.jsonl.tmp-*"))
        assert leftovers == []
    finally:
        store.close()
