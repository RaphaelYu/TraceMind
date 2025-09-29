# How-to: Policy Adapter (MCP)

`PolicyAdapter` tries MCP first, then falls back to local store.

- `get(arm) -> dict | None`
- `update(arm, params) -> dict`
- `list_arms() -> list[str]`

Configure with:
```python
PolicyAdapter(mcp=<MCPClient or None>, local=LocalPolicyStore(), timeout_s=5.0, prefer_remote=True)
```
