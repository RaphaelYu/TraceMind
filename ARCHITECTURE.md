# TraceMind Architecture

TraceMind is structured to keep AI-powered workflows governed, auditable, and free from runaway autonomy.
The README already lays out the problem space; this document spells out how the two primary planes and their artifacts work together, and why governance constraints are enforced before anything ever executes.

## Dual-Plane Model

TraceMind separates its responsibilities into two cooperating planes:

- **Design-Time Plane (Offline / Iteration)** — where intent, compilation, and verification happen before runtime. Users or assisted AI elaborate an Intent, compile it with declared plugins and policy into a WorkflowPolicy, and validate every artifact (schema, semantics, feasibility). Verification rejects any plan that violates policy, produces explanations or counterexamples, and manages versioned PatchProposals that need explicit approval.
- **Runtime Plane (Online / Execution)** — where governed agents execute only verified workflows under enforced policy and emit immutable traces as evidence. Agents are runtime nodes built from declared capabilities, the verified workflow, and governance. They may participate in an agent network, but only within the bounds of shared and local policies; they cannot self-authorize, self-evolve, or bypass guards.

These planes reflect the Intent → Compile → Verify → Run → Trace → Diagnose → Patch (Approved) → Iterate lifecycle described in the README.

## Artifacts and Evidence

All state in TraceMind is represented as explicit artifacts (Intent, Policy, Capability spec, WorkflowPolicy, Execution Trace, PatchProposal). There are no hidden decisions: every change or operation must map to a recorded, versioned artifact. This evidence-first approach enables deterministic governance, traceability, and replayability.

Artifacts also encode the system’s policies, including:

- **Constraints** (what must never happen)
- **Guards/Approval Pathways** (what requires human or higher-level consent)
- **Liveness expectations** (what must eventually happen)

## Responsibilities per Plane

### Design-Time Plane Responsibilities

- Translate customer requirements into Intent with clear goals, constraints, and preferences.
- Compile Intent + plugins + policies into a WorkflowPolicy that is runnable.
- Run verification (policy checks, bounded simulations, counterexamples) before handing anything to runtime.
- Manage PatchProposals for any change, and enforce approvals before runtime uptake.

### Runtime Plane Responsibilities

- Assemble agents from declared plugins, the verified workflow policy, and enforced governance.
- Execute workflows exactly as verified, emitting traces and state reports for each run.
- Reject or halt anything outside the verified policy.
- Support agent networks via events/messages while keeping each node within its boundaries.

## Governance and Boundaries

Governance is implemented in code, tests, and documentation:

1. **Policy as first-class** — every action must be justified by an artifact that codifies the policy that enabled it.
2. **Agent Boundaries** — agents are strictly runtime executors. They do not plan, self-authorize, or invoke capability APIs directly. Instead, agents follow the runtime workflow and interoperate through the workflow/runtime layers that mediate capability usage.
3. **Import Boundaries** — runtime code must not depend on agent inference/planning logic, and agents must not import capability execution interfaces directly; they rely on workflow/runtime abstractions.
4. **Trace Evidence** — every execution generates an immutable trace so auditors can understand what occurred and why.

These rules keep the runtime from drifting and keep the system governable rather than autonomous.

## Execution Lifecycle

1. Intent is drafted (customer or AI) and validated for schema and semantics.
2. WorkflowPolicy is compiled from declared plugins and policy guardrails.
3. Verification checks invariants, runs bounded simulations, and blocks disallowed plans.
4. The runtime instantiates an agent to execute the verified workflow.
5. Immutable execution traces are recorded and exposed for diagnostics.
6. Drift triggers PatchProposals that must be approved before they alter the runtime.

## Design Principles

- **No hidden state** — artifacts encode every decision and policy.
- **Explicit governance** — nothing runs without a policy path and approval.
- **Separation of concerns** — design-time reasoning is distinct from runtime execution; any interaction between planes uses well-defined artifacts and interfaces.
- **Evidence-first execution** — runtime outputs traces for every action, enabling auditing and replay.

By aligning implementation with this architecture, TraceMind ensures that agents remain governed executors and that the broader workflow stays safe, predictable, and auditable.
