# Recipe: LLM Call (FakeProvider)

Minimal example using the `ai.llm_call` step with FakeProvider (offline):

```yaml
steps:
  - id: hello
    type: ai.llm_call
    with:
      provider: fake
      model: fake-mini
      template: "Hello, {{name}}!"
      vars:
        name: Ruifei
```

Or from Python:

```python
import asyncio
from tm.steps.ai_llm_call import run

print(asyncio.run(run({
  "provider": "fake",
  "model": "fake-mini",
  "template": "Hello, {{name}}!",
  "vars": {"name": "Ruifei"}
})))
```
