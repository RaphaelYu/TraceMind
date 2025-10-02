### ai.llm_call (FakeProvider, runnable)

```python
import asyncio
from tm.steps.ai_llm_call import run

params = {
  "provider": "fake",
  "model": "fake-mini",
  "template": "Hello, {{name}}!",
  "vars": {"name": "Ruifei"},
  "timeout_ms": 5000,
}

print(asyncio.run(run(params)))
```

### ai.plan
```python
import asyncio
from tm.steps.ai_plan import run

params = {
  "provider": "fake",
  "model": "planner",
  "goal": "Sort numbers",
  "allow": {"tools": ["tool.sort"], "flows": []},
  "constraints": {"max_steps": 3},
}

print(asyncio.run(run(params)))
```

### ai.execute_plan
```python
import asyncio
from tm.steps.ai_execute_plan import run
from tm.flow.runtime import FlowRuntime

# Provide a FlowRuntime instance and a validated plan
runtime = FlowRuntime()
plan = {
  "version": "plan.v1",
  "goal": "demo",
  "constraints": {},
  "allow": {"tools": [], "flows": []},
  "steps": [],
}

print(asyncio.run(run({"plan": plan, "runtime": runtime})))
```

### ai.reflect
```python
import asyncio
from tm.steps.ai_reflect import run

params = {
  "provider": "fake",
  "model": "reflector",
  "recent_outcomes": {"s1": {"status": "ok"}},
  "retrospect_stats": {},
}

print(asyncio.run(run(params)))
```

### Memory helpers
```python
import asyncio
from tm.steps.memory_set import run as memory_set
from tm.steps.memory_get import run as memory_get

async def main():
    await memory_set({"session_id": "demo", "key": "answer", "value": 42})
    print(await memory_get({"session_id": "demo", "key": "answer"}))

asyncio.run(main())
```

### Retry + timeout
```python
import asyncio
from tm.steps.ai_llm_call import run

params = {
  "provider": "fake",
  "model": "fake-mini",
  "prompt": "ping",
  "timeout_ms": 1,
  "max_retries": 1,
}
print(asyncio.run(run(params)))
```
