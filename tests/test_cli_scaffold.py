from pathlib import Path

from tm.scaffold import create_flow, create_policy, init_project


def test_init_project_creates_structure(tmp_path: Path):
    root = init_project("demo", tmp_path)
    assert (root / "trace-mind.toml").exists()
    assert (root / "flows" / "hello.py").exists()
    assert (root / "policies" / "default_policy.py").exists()
    assert (root / "scripts" / "run_local.sh").exists()


def test_create_flow_variants(tmp_path: Path):
    root = init_project("demo", tmp_path)
    flow_file = create_flow("greet", project_root=root, switch=True)
    content = flow_file.read_text("utf-8")
    assert "Operation.SWITCH" in content


def test_create_policy_updates_config(tmp_path: Path):
    root = init_project("demo", tmp_path)
    create_policy("traffic", project_root=root, strategy="ucb", mcp_endpoint="mcp:policy")
    config = (root / "trace-mind.toml").read_text("utf-8")
    assert 'policy_endpoint = "mcp:policy"' in config
    policy_file = root / "policies" / "traffic.py"
    assert policy_file.exists()
    assert "confidence" in policy_file.read_text("utf-8")
