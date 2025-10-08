import pytest

from tm.pipeline.selectors import match, parse


def test_match_supports_wildcards_and_indices():
    assert match("a.b[].c", ("a", "b", 2, "c")) is True
    assert match("a.*.z", ("a", "anything", "z")) is True
    assert match("root.items[3]", ("root", "items", 3)) is True
    assert match("root.items[0]", ("root", "items", 1)) is False


def test_match_requires_complete_path():
    assert match("top.child", ("top",)) is False
    assert match("top[*]", ("top", 0)) is False


def test_parse_rejects_unclosed_brackets():
    with pytest.raises(ValueError):
        parse("a.b[1")
