"""Tests for the secrets/redaction helpers."""

from pathlib import Path

from tm.security.redaction import Redactor
from tm.security.secrets import SecretStore


def test_secret_store_persists(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    store = SecretStore(workspace_root)
    assert store.list() == []
    store.add("top-secret")
    assert "top-secret" in store.list()
    store.add("  top-secret  ")
    assert store.list().count("top-secret") == 1
    secrets_path = workspace_root / ".tracemind" / "secrets.yaml"
    assert secrets_path.exists()


def test_redactor_masks_nested_values() -> None:
    redactor = Redactor(["alpha", "beta"], mask="XX")
    assert redactor.redact_string("alpha-beta") == "XX-XX"
    payload = {
        "hint": "alpha once",
        "list": ["beta", {"nested": "alpha-beta"}],
        "number": 5,
    }
    masked = redactor.redact(payload)
    assert masked["hint"] == "XX once"
    assert masked["list"][0] == "XX"
    assert masked["list"][1]["nested"] == "XX-XX"
