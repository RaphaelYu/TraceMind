T-LLM-01 · Zero-conflict scaffold

How to apply:
1) Create a feature branch:
   git checkout -b feat/t-llm-01-llm-client

2) Unzip this package at the repo root (it only adds new files):
   unzip tracemind_t-llm-01_scaffold.zip -d <your repo root>

3) Quick smoke tests (no network needed):
    pytest -q

4) Try the runnable example (adapt to your runner if needed):
   # If you have a runner: tm run examples/llm/hello_fake.yaml
   # Or in Python REPL, paste the snippet from docs/recipes-v1.md

Notes:
  - No existing files are modified.
  - Recorder integration is via tm.ai.recorder_bridge (no-op if missing).
  - OpenAI provider needs an async transport to actually call the API; fake provider works offline.
