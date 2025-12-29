# TraceMind Runtime Agents

Runtime agents are deterministic programs that move data through the TraceMind runtime pipeline. They are _not_ open-ended AI agents; rather, each runtime agent exposes a fixed IO contract, accepts strictly declared inputs, and produces explicit outputs so that executions can be verified and audited automatically. Runtime agents are assembled into `agent_bundle` artifacts whose integrity is ensured before anything is run.

## From requirements to execution

1. **Author the IO contract** – For every runtime agent you describe inputs, outputs, and side effects via IORefs and effects (see `docs/io_contract_v0.md`). This contract becomes part of the `agent_bundle` spec so verifiers can reason about closure, typing, and idempotency without executing the code.
2. **Bundle the agents** – A bundle YAML (see `specs/examples/agent_bundle_v0/agent_bundle_demo.yaml`) lists every agent spec plus a linear plan that wires inputs/outputs across steps. You can register builtin agents such as `tm-agent/noop:0.1`, `tm-agent/http-mock:0.1`, and `tm-agent/shell:0.1` via `tm.agents.builtins`.
3. **Verify the artifact** – The CLI command `tm artifacts verify <bundle.yaml>` inspects the bundle, runs IO contract linting (`tm.lint.io_contract_lint`), and computes a deterministic body hash. Only `candidate` artifacts that pass verification can be accepted and run.
4. **Run with governance** – `tm run bundle <accepted.yaml> --inputs <ref>=<json> --report <path>` executes the plan inside `tm.runtime.executor.AgentBundleExecutor`. The executor enforces policy guards (`tm.policy.guard.PolicyGuard`), records evidence (`ExecutionContext.evidence`), and emits structured run reports summarizing per-step outputs, policy decisions, and agent-specific evidence.

## Policy and evidence

Resource effects declared in each agent are evaluated against the allowlist defined in the bundle metadata (`meta.policy.allow`) plus the global defaults (`tm.policy.policies_v0`). The `PolicyGuard` records every decision as `policy_guard` evidence, and executions fail fast if a denied effect would fire. This keeps agents fail-closed unless resources are explicitly approved.

Each runtime agent can call `self.add_evidence(kind, payload)` so the executor can persist agent-specific traces (stdout dumps, mocked HTTP responses, hashes, etc.). These entries show up in the run report alongside policy decisions, idempotency cache hits, and audit logs emitted by `ExecutionContext`.

## Running a bundle

Minimal commands for the golden bundle:

```bash
tm artifacts verify specs/examples/agent_bundle_v0/agent_bundle_demo.yaml
tm artifacts accept specs/examples/agent_bundle_v0/agent_bundle_demo.yaml --out tmp/artifacts
tm run bundle tmp/artifacts/tm-agent-bundle-demo.yaml \
  --inputs artifact:http_request='{"method":"GET","url":"https://example.com/api/demo"}' \
  --report tmp/run/report.yaml
```

Because the shell step in this bundle lacks the required resource allowlist, the executor emits a policy denial and the report records the failed step and denied target. The previous steps still surface their outputs (`artifact:http_response`, `state:noop.out`), enabling downstream tooling to inspect what completed before failure.

## What makes runtime agents reliable

- **Determinism:** Agents must return the same outputs for the same inputs (no hidden randomness or network calls). Builtin helpers such as `tm-agent/http-mock:0.1` rely entirely on deterministic config maps.
- **IO contract closure:** Every effect target is declared in the agent’s IORefs (see `docs/io_contract_v0.md`), and plans are linted to make sure data flows follow the declared inputs/outputs before execution.
- **Idempotency:** Resource effects declare idempotency keys so repeated bundle runs reuse cached outputs instead of re-running the agent unnecessarily. For example, a keyed effect might list `artifact_id` or `command` so the runtime can reuse prior results safely.

Together, these controls keep runtime agents auditable, verifiable, and safe to execute inside CI/CD pipelines, policy guard workflows, or local experiments.
