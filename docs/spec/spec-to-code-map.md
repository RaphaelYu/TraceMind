# Spec-to-Code Map

## Methodology
- Reviewed `docs/semantic-spec-v0` as the only authoritative source for Phase 0 requirements.
- Focused on the code paths currently exercised by the CLI/runtime/governance stack; each module below notes the spec chapters it is trying to satisfy, the artifacts it creates/reads/validates, and any behavior we could not map to the spec.
- Any module or behavior that could not be linked directly to a semantic concept is reported as a potential violation of Task 0.1.

---

## Module: `tm/cli.py` & `tm/cli/*`
- **Spec chapters**: `docs/semantic-spec-v0/11-ui-and-cli-mapping.md` (command/interaction surface) plus `docs/semantic-spec-v0/12-reference-workflow.md` (flow validation hooks) and `docs/semantic-spec-v0/02-artifact-overview.md` (CLI orchestrates artifacts).
- **Artifacts**: CLI reads `flows/*.yaml` (implicit `WorkflowPolicy` drafts), feeds them into `FlowRuntime` (creates `ExecutionTrace` entries via `FlowTraceSink`), dispatches `PolicySpec` and `Flow` validation (`tm/cli/validate` → `tm/validate/static.py`), and surfaces approval/daemon status (`PolicySpec`/`IntegratedStateReport` status snapshots) in the UI.
- **Implicit behavior / spec gaps**: scaffolding helpers (`tm/scaffold.*`), signal handling, daemon management, file-system copy/templating are not described in the semantic spec; they exist purely for developer ergonomics and introduce OS-level side effects without artifact-level tracing.

## Module: `tm/scaffold` (project/flow/policy scaffolding)
- **Spec chapters**: None—scaffolding is not described in `semantic-spec-v0`.
- **Artifacts**: writes boilerplate flow/policy/step files that ML, CLI, or developers might later turn into `IntentSpec`/`CapabilitySpec`/`WorkflowPolicy` artifacts, but the code itself never produces a spec-compliant artifact.
- **Implicit behavior / spec gaps**: performs filesystem mutations, slug normalization, TOML writes, step stub injection without audit trails; the operation is opaque to the spec and should be considered a violation until its output is expressed purely as traced artifacts.

## Module: `tm/flow` package (`Flow`, `FlowSpec`, `FlowRuntime`, `FlowTraceSink`, `FlowPolicies`)
- **Spec chapters**: `docs/semantic-spec-v0/02-artifact-overview.md` (defines `WorkflowPolicy`, `ExecutionTrace`), `docs/semantic-spec-v0/07-composer-specification.md` (assembly of steps into workflows), `docs/semantic-spec-v0/09-runtime-and-execution.md` (execution semantics, guards, trace recording).
- **Artifacts**: `FlowSpec` models a `WorkflowPolicy`; `FlowRuntime.run/execute` consumes that spec, enforces `GuardDecision`s, and generates `FlowRunRecord` + `TraceSpanLike` entries that become `ExecutionTrace`s in `FlowTraceSink`. `FlowPolicies` provide per-flow response/concurrency knobs that claim to represent runtime policy boundaries.
- **Implicit behavior / spec gaps**: composition (FlowSpec creation) and execution live in the same package; the spec expected a Composer to explain how an `IntentSpec` becomes a `WorkflowPolicy` (chapters 04 + 07), but this code never sees `IntentSpec` and therefore collapses two roles. It also holds idempotency caching, queueing, and metrics counters that are not articulated in the spec (see `FlowRuntime._cache`, queue management, `FlowPolicies`).

## Module: `tm/runtime` package (`engine`, `queue`, `workers`, `idempotency`, `retry`)
- **Spec chapters**: `docs/semantic-spec-v0/09-runtime-and-execution.md` (engine config, execution guarantees, guard points) and `docs/semantic-spec-v0/06-semantic-state-model.md` (state isolation via deterministic engines).
- **Artifacts**: configures a runtime engine (`tm/dsl.runtime.Engine`) that executes `WorkflowPolicy` DAGs and surfaces `ExecutionTrace`/`FlowRunRecord` plus `IntegratedStateReport` cues via the governor. `tm/runtime/queue` ensures that each `Flow` execution stays serialized and that `ExecutionTrace`s can be correlated with requests.
- **Implicit behavior / spec gaps**: `tm/runtime` binds to concrete Python/Process engines, file-based queues, DLQ handling, idempotency keys, retry policies, and signal installation—features the spec does not explicitly talk about and which currently rely on hidden state rather than artifact declarations.

## Module: `tm/policy` package (`PolicyAdapter`, `LocalPolicyStore`, `transports`)
- **Spec chapters**: `docs/semantic-spec-v0/05-policy-specification.md` (policy schema, validation, guards). Storage/backing maps are the implementation of `PolicySpec` persistence.
- **Artifacts**: stores policy arms (`PolicySpec`) and responds with policy parameters; `PolicyAdapter.update` is used during governance to record `PatchProposal` effects. `LocalPolicyStore.snapshot` can be interpreted as producing auditable policy versions.
- **Implicit behavior / spec gaps**: the use of an MCP remote client is not mentioned in the spec, so remote fetch/update fall outside of the declared semantics. The module also includes direct JSON-RPC calls, optimistic syncing, and fallback to local storage—network behaviors that cannot be traced via the official artifacts.

## Module: `tm/guard` package (`GuardEngine`, built-in rules)
- **Spec chapters**: `docs/semantic-spec-v0/05-policy-specification.md` (section 5.8 Guard semantics) and `docs/semantic-spec-v0/09-runtime-and-execution.md` (section 9.5 Guard enforcement).
- **Artifacts**: accepts guard rules (part of `PolicySpec`/`WorkflowPolicy`), evaluates payloads before runtime executes steps, and emits `GuardViolation` objects that feed into `IntegratedStateReport` or CLI errors.
- **Implicit behavior / spec gaps**: exposes built-in helpers (`length_max`, `regex_deny`, etc.) that assume specific payload shapes and string handling; those semantics are not described in the spec, so we must treat the rule library as an implicit extension of the guard concept.

## Module: `tm/governance` package (`manager`, `hitl`, `audit`, `ratelimit`, `budget`, `breaker`)
- **Spec chapters**: `docs/semantic-spec-v0/10-iteration-and-governance.md` (governance loop, patch proposal management, approval, budgets) plus `docs/semantic-spec-v0/08-verification-and-monitoring.md` (audit, metrics) and `docs/semantic-spec-v0/09-runtime-and-execution.md` (governance as pre-execution filter).
- **Artifacts**: orchestrates `PatchProposal` (through `tm/ai/proposals` + `PolicyStore`), produces `GovernanceDecision` records that gate runtime executions, writes audit entries (`AuditTrail` + `BinaryLogWriter`), and enforces limits via `BudgetTracker`/`RateTracker` for `PolicySpec` updates.
- **Implicit behavior / spec gaps**: the implementation adds rolling windows, circuit breakers, and queue size tracking beyond the textual spec; those are governance-level heuristics that should eventually be expressed purely as artifacts (e.g., timeline of `LimitReservation`s) but currently live as hidden state.

## Module: `tm/ai` package (`policy_store`, `proposals`, `controller`, `llm_client`, `run_pipeline`, `tuner`, `retrospect`...)
- **Spec chapters**: `docs/semantic-spec-v0/04-intent-specification.md` (AI boundary for intents), `docs/semantic-spec-v0/10-iteration-and-governance.md` (PatchProposal structure + AI’s proposal-only right), and `docs/semantic-spec-v0/12-reference-workflow.md` (AI must remain artifact-only during reference flows).
- **Artifacts**: `Proposal`/`Change` describe `PatchProposal`s, `PolicyStore` versioning yields auditable policy artifacts, and `AIController` records proposal lifecycle events to binary logs so patches can be audited.
- **Implicit behavior / spec gaps**: the package also includes LLM clients, reward-weight tuning, `Retrospect` ingestion, and `BanditTuner` updates that expose AI decision-making beyond mere artifact drafting; these operations depend on external models, create hidden reward signals, and are currently undocumented in the spec (violates the “AI has no authority” promise unless strictly limited to proposal drafting).

## Module: `tm/verify` package (`Explorer`, `TraceMindAdapter`, `load_spec`, `build_report`)
- **Spec chapters**: `docs/semantic-spec-v0/08-verification-and-monitoring.md` (invariant checking, counterexample generation, reporting) and `docs/semantic-spec-v0/12-reference-workflow.md` (ensuring workflows can be expressed as artifacts).
- **Artifacts**: loads `VerifySpec` (invariants + store), executes plans described as `tm/pipeline.Plan`, and emits `IntegratedStateReport`/`ExecutionTrace` candidates when invariants fail; also produces human-readable reports via `build_report` that map back to policy artifacts.
- **Implicit behavior / spec gaps**: the verifier currently assumes JSON/YAML plan formats and uses the `tm.pipeline` tracing API; the spec demands richer counterexamples, so this module should be expanded once the format is normalized.

## Module: `tm/pipeline` package (`Plan`, `Rule`, `AnalysisReport`, `Pipeline` execution)
- **Spec chapters**: `docs/semantic-spec-v0/07-composer-specification.md` (plan/rule structure) and `docs/semantic-spec-v0/08-verification-and-monitoring.md` (static analysis, conflict detection, coverage reporting).
- **Artifacts**: `Plan` ↔ `WorkflowPolicy` rules, `TraceSpan` ↔ `ExecutionTrace`, `AnalysisReport` ↔ `IntegratedStateReport` of static conflicts. `tm/pipeline.analysis` computes dependency graphs, coverage metrics, and conflict listings that feed into acceptance criteria `AC-VER-*`.
- **Implicit behavior / spec gaps**: the analysis currently relies on heuristic selectors (first-token matching) for read/write overlap; these heuristics are not specified in the semantic spec and should be documented if kept.

## Module: `tm/obs` + `tm/storage` packages (`Recorder`, `FlowTraceSink`, `BinaryLogWriter`)
- **Spec chapters**: `docs/semantic-spec-v0/08-verification-and-monitoring.md` (monitoring records, audit/logging) and `docs/semantic-spec-v0/02-artifact-overview.md` (ExecutionTrace storage, audit of `IntegratedStateReport`).
- **Artifacts**: `Recorder` emits counters/timers tied to flow execution, policy violations, pipeline steps, and tuner rewards; `FlowTraceSink` writes `TraceSpanLike` objects to `BinaryLogWriter`, producing persistent `ExecutionTrace` logs that can be replayed by governance or verification.
- **Implicit behavior / spec gaps**: the binary log format is proprietary without schema descriptions in the spec; the recorder also assumes a knowledge store (`tm.kstore`) not mentioned anywhere.

## Module: `tm/validate` package (`find_conflicts`, CLI validator)
- **Spec chapters**: `docs/semantic-spec-v0/07-composer-specification.md` (step/rule locking) and `docs/semantic-spec-v0/08-verification-and-monitoring.md` (static conflict detection).
- **Artifacts**: reads flow/policy YAML files and exposes conflicts that would violate `WorkflowPolicy` invariants before runtime; outputs a soft `IntegratedStateReport` (in text/JSON) describing issues.
- **Implicit behavior / spec gaps**: introduces domain-specific conflict kinds (lock mode, cron overlap) that are not yet expressed as artifacts and therefore need to be aligned with the official invariant vocabulary.

## Module: `tm/connectors` package (`docker`, `k8s`, `mcp` connectors)
- **Spec chapters**: None—the semantic spec does not describe any concrete connectors.
- **Artifacts**: these modules perform side-effecting API calls (Docker REST, Kubernetes, MCP) outside the artifact graph.
- **Implicit behavior / spec gaps**: violates Task 0.1’s requirement that every capability be named and validated by a `CapabilitySpec`. These connectors pave the way for executing external functionality without a declared capability, so they must either be wrapped by explicit `CapabilitySpec`s or removed from the Phase 0 deliverable.

---

## Missing spec artifacts / violations
1. **`IntentSpec` & Intent validation/composition**: there is no module that defines `IntentSpec`, validates it, or feeds it into the Composer (see `docs/semantic-spec-v0/04-intent-specification.md`). The reference workflow (Chapter 12) depends on intents, but the repo currently bypasses them entirely. This is a critical gap.
2. **`CapabilitySpec` catalog**: no code defines `CapabilitySpec` (schema, registry, validation) as required by `docs/semantic-spec-v0/03-capability-specification.md`. Hence there is no declared ability catalog, which is a hard violation of Phase 1 expectations.
3. **AI boundary enforcement**: `tm/ai` handles proposals, tuning, and heuristics, but the semantic spec requires that AI may only produce `IntentSpec` or `PatchProposal` artifacts (`docs/semantic-spec-v0/04-intent-specification.md`, `docs/semantic-spec-v0/10-iteration-and-governance.md`). The rich tuner/retrospect workflow touches runtime events and policy storage without producing the mandated artifacts, so additional guard rails (or removal) are required.
4. **Connector side effects**: as noted above, `tm/connectors` makes Docker/K8s/MCP calls without a wrapped capability; this is implicitly executing behavior outside the spec’s artifact graph.

---

## Conclusions
- The current codebase provides a runtime/composer stack (`tm/flow`, `tm/runtime`, `tm/governance`, `tm/policy`, `tm/guard`, `tm/verify`, `tm/pipeline`, `tm/obs`), but it lacks explicit `IntentSpec`/`CapabilitySpec` artifacts, and several convenience bundles (`tm/scaffold`, `tm/connectors`, `tm/ai/tuner`) introduce side effects not described in the semantic spec.
- To meet Phase 0, we must (a) document the missing artifacts, (b) set up explicit validation modules for Intent/Capability, and (c) either align or remove the undocumented helper modules.
