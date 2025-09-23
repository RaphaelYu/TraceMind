from tm.flow.engine import Engine


def test_get_path_from_nested_vars():
    root = {
        "vars": {"task": {"result": 42}},
        "inputs": {"payload": "ignored"},
        "cfg": {},
    }

    value = Engine._get_path(root, "$.vars.task.result")

    assert value == 42
