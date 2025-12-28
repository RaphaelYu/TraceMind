from tm.artifacts.hash import body_hash
from tm.artifacts.normalize import normalize_body


def test_normalize_body_is_deterministic() -> None:
    base = {
        "goal": "  deliver report\r\nwith clarity ",
        "actors": ["system", "user"],
        "metadata": {"updated": "2024-01-01T00:00:00Z", "tags": ["important", "draft"]},
        "constraints": ["keep audit trail", "minimize cost"],
        "details": {"summary": "Result", "priority": "high"},
    }
    variant = {
        "metadata": {"tags": ["important", "draft"], "updated": "2024-01-01T00:00:00Z"},
        "constraints": ["keep audit trail", "minimize cost"],
        "goal": "deliver report\nwith clarity",
        "actors": ["system", "user"],
        "details": {"priority": "high", "summary": "Result"},
    }
    normalized_base = normalize_body(base)
    normalized_variant = normalize_body(variant)
    assert normalized_base == normalized_variant
    assert body_hash(base) == body_hash(variant)


def test_body_hash_ignores_whitespace_only_changes() -> None:
    payload = {"title": " Line with spaces ", "description": "three\r\nlines\rbe careful"}
    trimmed = {"description": "three\nlines\nbe careful", "title": "Line with spaces"}
    assert body_hash(payload) == body_hash(trimmed)
