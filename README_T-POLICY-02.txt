T-POLICY-02 · MCP policy adapter (zero-conflict)

What you get:
  - tm/policy/local_store.py: simple async in-memory policy store
  - tm/policy/mcp_client.py: minimal JSON-RPC2 client with pluggable transport
  - tm/policy/transports.py: InProcessTransport (test/dummy)
  - tm/policy/adapter.py: PolicyAdapter with MCP-first, fallback-to-local logic
  - docs/policy.md: runnable examples
  - tests/test_policy_adapter.py

Apply:
  git checkout -b feat/t-policy-02-mcp-adapter
  unzip tracemind_t-policy-02_scaffold.zip -d <repo root>
  # Ensure repo root is on PYTHONPATH (pytest.ini or env var)
  pytest -q

Notes:
  - No existing files are modified.
  - Transport is abstract; plug your real MCP transport later.
  - All I/O paths are async and non-blocking.
