# TraceMind Charter

## Mission

TraceMind is not a product sprint; it is an **independent, general, governable AI assistance core**.
Its sole responsibility is to operate strictly within a frozen semantic specification that defines
the system’s artifact model, composition constraints, policy guardrails, verification rules,
runtime responsibilities, and governance loops.

This specification is the single source of truth for the system.
Every feature, CLI command, artifact, and test must be directly traceable to that specification.
Any behavior that cannot be expressed through the canonical artifacts, enforced policies,
reference workflows, and explicit approval loops is considered invalid by design.

## Core Principles (from 01. Concepts & Roles)

1. **AI has no execution authority.** AI may only propose `IntentSpec` or `PatchProposal`; it never directly runs capability code.
2. **Everything is verifiable.** Every automation decision must survive schema validation, semantic checks, or monitoring counters (traces and counterexamples must exist).
3. **Semantics before implementation.** We care about what the system is allowed to do, not how the code does it; the codebase simply implements the artifacts.
4. **Artifacts over code.** Artifacts (Intent, Capability, Policy, Workflow, Trace, Report, Patch) are the system's ground truth.
5. **UI/CLI are not truth sources.** Interfaces only create, modify, or inspect artifacts; truth comes from the validated artifacts plus runtime evidence.

## Artifact Doctrine (02. Artifact Overview)

TraceMind defines a canonical artifact set (`IntentSpec`, `CapabilitySpec`, `PolicySpec`, `WorkflowPolicy`, `ExecutionTrace`, `IntegratedStateReport`, `PatchProposal`). These artifacts must be serializable (YAML/JSON), verifiable (schema + deterministic rules), composable, auditable, and execution-decoupled. The lifecycle flows from declaration to intent, composition, verification, runtime execution, judgment, and then iteration. Artifacts are immutable; updates require versioned replacements. Dependencies are strictly acyclic—no runtime mutates a capability spec, and traces cannot influence intents.

## Phase 0—Spec Compliance (Tasks 0.1 & 0.2)

1. **Spec-to-code mapping** (`docs/spec/spec-to-code-map.md`): enumerate every core module, name the spec chapter it implements (02–07), describe which artifact it produces/consumes, and flag any implicit behavior that lacks a spec anchor; violations are disallowed.
2. **Reference Workflow review** (`docs/spec/reference-workflow-review.md`): exercise the Reference Workflow artifacts—capabilities, intent, policy, violation, patch—and document whether the spec vocabulary is sufficient to express every step without “dark knowledge,” missing fields, or semantic contradiction.

## Reference Workflow Blueprint (12. Reference Workflow)

The reference workflow illustrates the minimum closed loop that TraceMind must run. Its abstract story: produce a result, validate it, and ensure unauthorized external writes never happen. The declared capabilities are:

* `compute.process`: deterministic internal computation that emits `computation.completed`.
* `validate.result`: validation step that produces `result.validated`.
* `external.write`: side-effectful write guarded by approvals and irreversible safety contracts.

A PolicySpec defines the state schema (`computation.completed`, `result.validated`, `external.write.performed`) plus invariants (never write externally without validation) and a liveness requirement (eventually `result.validated`). The IntentSpec asks to achieve `result.validated` under safety constraints. The composer must reject governance-violating candidate workflows, expose deterministic explanations, and only emit workflows that pass verification. The workflow must demonstrate generation, validation, execution, violation detection, patch proposal, approval, and a rerun with a corrected policy/artifact path.

## Phase 1 Scope—Minimal Implementations

1. **Artifact Schemas (02)**: Define JSON/YAML schemas for each artifact and provide a validation API that rejects invalid structures; no business logic resides in the schema layer.
2. **Capability Catalog (03)**: Support capability registration, schema validation, and catalog queries. Each capability spec enumerates inputs, outputs, configuration schema, declared event types, state extractors, and safety contracts (including determinism and rollback capabilities).
3. **Intent Validator (04)**: Validate that intents describe desired goals, constraints, preferences, and context refs without mention of steps, rules, or capability IDs; report over/under-constrained failures.
4. **Composer v0 (07)**: Run the Reference Workflow composer that combines IntentSpec + capability catalog + PolicySpec to deterministically emit ranked `WorkflowPolicy` candidates with explanations, summary of discarded options, and deterministic ordering; reject plans that violate invariants or safety contracts.
5. **Verifier v0 (08)**: Provide multi-layer verification (schema, semantic, static policy, simulation), detect violations, and emit counterexamples (minimal paths with capability actions) for any unsafe workflow; monitoring hooks must replay traces.
6. **Runtime v0 (09)**: Execute workflows step-by-step (guards, sequential/parallel flows) without decision-making, produce immutable `ExecutionTrace` events, and feed monitors/violation reports to the verifier. Runtime strictly follows the workflow, does not modify policy, never infers missing inputs, and records every guard/step outcome.
7. **Iteration Loop v0 (10)**: When violations or deviations occur, emit `IntegratedStateReport`, generate `PatchProposal` entries (source, target, rationale, expected effect), enforce validation/simulation/approval before applying a higher-version artifact, and rerun the reference workflow; governance prohibits runtime self-modification, enforces approvals, version DAGs, and rollback via workflows traced like any other artifact.

## Unified Redlines

* No business logic or external execution in this phase.
* AI never builds workflows directly—it only proposes intents or patches.
* Runtime does not negotiate, decide policies, or fix violations.
* CLI/GUI actions cannot bypass artifact-based validation.
* Features must map to a spec chapter before being implemented (“spec-first”).

## Governance Boundaries (from 10.8)

The spec codifies explicit governance and operational boundaries so TraceMind never drifts toward ad-hoc behavior:

* **Runtime stovepipes**: Runtime only executes declared `WorkflowPolicy` steps, never mutates policies or infers missing inputs, and strictly obeys guard semantics (approval, rate-limit, isolation) before executing a capability (`docs/semantic-spec-v0/09-runtime-and-execution.md`).
* **Artifact immutability**: Every artifact (Intent, Capability, Policy, Workflow, Trace, Report, Patch) is immutable and versioned; updates happen through governance-approved PatchProposals that produce new artefact versions (`docs/semantic-spec-v0/02-artifact-overview.md`, `10-iteration-and-governance.md`).
* **AI scope lock**: AI cannot execute capabilities or Runtime; it can only emit IntentSpecs or PatchProposals subject to validation and approval (`docs/semantic-spec-v0/01-concepts-and-roles.md`, `10-iteration-and-governance.md`).
* **No spontaneous evolution**: Changes can only originate from explicit violations, degradations, intent/capability/policy updates, and must proceed through validation, simulation, approval, apply, and observe stages documented in the reference workflow (`docs/semantic-spec-v0/10-iteration-and-governance.md`).
* **Policy-first permissioning**: Nothing happens without a policy allowing it—capability activations, guard approvals, liveness expectations, invariants, and approvals all derive from the PolicySpec schema; any deviation is treated as a violation (`docs/semantic-spec-v0/05-policy-specification.md`, `13-acceptance-criteria.md`).

## Acceptance Criteria Summary (13. Acceptance Criteria)

* **Artifact level**: intents/capabilities/policies/workflows/traces/reports must all be schema-validated, immutable, and free of hidden semantics.
* **Composer**: legality, determinism, explainability, and diagnosable failure reasons.
* **Verification & monitoring**: static refusals, simulation counterexamples, runtime invariant catching, consistent judgments.
* **Runtime**: executes only verified workflows, traces every unit, exposes only declared concurrency, and generates replayable traces.
* **Iteration & governance**: no spontaneous evolution, every change backed by a `PatchProposal`, versioned rollout with rollback paths, AI limited to proposals.
* **UI/CLI parity**: CLI or UI actions are semantically equivalent, avoid UI-only shortcuts, and keep drafts isolated.
* **Reference Workflow**: full intent → composer → execution → violation → patch → rerun loop; violations reproducible and patched workflows pass.

## Final Admission Questions

1. Can every line of code cite the spec chapter and artifact it implements?
2. Is the Reference Workflow fully reproducible with the declared artifacts?
3. Is there any pathway that bypasses verification and executes without policy enforcement?

Failure to answer any of these in the affirmative means TraceMind has not yet met the charter. The charter’s final warning endures: **TraceMind’s goal is not to be convenient, it is to be uncontrollable; constraints come before capabilities.**
