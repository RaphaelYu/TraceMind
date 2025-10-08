import os

from tm.kstore.api import open_kstore
from tm.kstore.jsonl import JsonlKStore


def test_fallback_to_jsonl_when_sqlite_unavailable(tmp_path, monkeypatch):
    url = f"sqlite://{tmp_path}/missing.db"
    monkeypatch.setenv("TM_KSTORE", url)
    monkeypatch.setenv("NO_SQLITE", "1")

    ks = open_kstore(os.getenv("TM_KSTORE"))
    try:
        ks.put("k:v", {"v": 1})
        assert ks.get("k:v") == {"v": 1}
    finally:
        ks.close()

    assert isinstance(ks, JsonlKStore)
