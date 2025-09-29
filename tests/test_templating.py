import pytest
from tm.utils.templating import render_template

def test_render_ok():
    out = render_template("Hi {{x}}", {"x": 123})
    assert out == "Hi 123"

def test_missing_var_raises():
    with pytest.raises(KeyError):
        render_template("Hi {{x}}", {})
