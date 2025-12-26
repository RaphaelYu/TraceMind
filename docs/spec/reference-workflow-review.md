# Reference Workflow Review

This review follows Task 0.2: analyze the Reference Workflow in `docs/semantic-spec-v0/12-reference-workflow.md` and verify that every step can be expressed purely with the canonical artifacts (CapabilitySpec, PolicySpec, IntentSpec, WorkflowPolicy, ExecutionTrace, Violation/IntegratedStateReport, PatchProposal) without relying on unstated assumptions.

## 1. Capability Set (Section 12.4)
- ✅ The three capabilities (`compute.process`, `validate.result`, `external.write`) detail `capability_id`, `version`, `inputs`, `event_types`, `state_extractors`, and `safety_contract`, so they can each be encoded as `CapabilitySpec`.
- ⚠️ The samples omit a `description` field and `config_schema` entries even though Section 3.3.1 lists them; while these may be optional, the absence should be clarified because downstream tooling (composer/validation) may expect every capability to specify its safe bounds explicitly.

## 2. PolicySpec (Section 12.5)
- ⚠️ The fragment lacks the required top-level metadata (`policy_id`, `version`, `metadata`, `guards`) defined in Section 5.4.1. Without `policy_id`/`version`, the policy cannot be registered or audited, and guards cannot be attached to the policy or referencing workflows.
- ✅ `state_schema`, `invariants`, and `liveness` are present; the invariant succinctly encodes `never external.write.performed && !result.validated`, and the liveness clause (`result.validated` eventually true) matches the Reference Workflow narrative.
- ⚠️ No guard is defined despite Sections 5.8 & 9.5 insisting on explicit guard declarations when execution requires approval (the workflow explicitly mentions `external.write (guarded)` but the policy snippet never declares that guard). This means the workflow cannot be fully expressed as artifacts because the guard dependency is missing.

## 3. IntentSpec (Section 12.6)
- ⚠️ The intent sample omits `version` (Section 4.4.1) and `context_refs`. Without `version`, intents cannot be versioned or compared; without context references, the composer loses linkage to the `PolicySpec`/`CapabilitySpec` context it needs.
- ⚠️ The constraint `rule: no_unvalidated_external_write` has no matching definition anywhere in the policy or capability documents. Section 4.6 expects constraints to reference concrete, named semantics (e.g., policy invariants or guard rules). Because the policy invariant is unnamed, there is no canonical artifact to satisfy the constraint, so the constraint cannot be compiled unless a naming convention is established.
- ✅ The goal and preferences follow the schema.

## 4. Composer Output / WorkflowPolicy (Section 12.7)
- ⚠️ The “candidate” and “approved” workflows are shown purely as text sequences of capability IDs; no structured `WorkflowPolicy` artifact (with steps, transitions, guard annotations, or explanations) is provided. Section 7.3.2 requires each candidate to include an explanation, risk assessment, and verification precondition. Because only textual lists appear, there is no artifact to feed into verification/execution—a concrete `WorkflowPolicy` schema must be detailed.
- ⚠️ The approved workflow mentions `external.write (guarded)` but does not state how the guard is attached (policy guard vs. workflow guard) nor what the guard parameters are. The Reference Workflow therefore cannot be coded without inventing those guard artifacts.

## 5. Execution Trace (Section 12.8)
- ✅ A minimal stream of events is shown (`compute.process.done`, `validate.result.passed`, `external.write.done`), which is sufficient to describe an `ExecutionTrace` for the happy path.
- ⚠️ The trace lacks timestamps, state references, or identity metadata (run ID, capability version). While Section 9.2 allows simplified traces, the spec requires traces to be uniquely identifiable; this example should annotate at least the run identifier and step ordering to guarantee determinism.

## 6. Violation / IntegratedStateReport (Section 12.9)
- ✅ The violation example shows the event sequence without the validation step, as required.
- ⚠️ The `IntegratedStateReport` names the violated rule `invariant.no_unvalidated_external_write`, but the policy did not assign any name to its invariant (it only gave a logical condition). Without a named invariant, the report cannot reference `policy.invariant.*` as demanded by Section 8.8. The Reference Workflow must therefore specify invariant identifiers.
- ✅ The evidence and blame fields follow the structure prescribed in Section 8.8.

## 7. PatchProposal (Section 12.10)
- ⚠️ The provided patch lacks `proposal_id` and `rationale` fields listed in Section 10.3.2. The spec mandates that every patch proposal be uniquely identifiable and provide a rationale for governance/audit; without these, the patch cannot be traced or approved.
- ✅ The remaining fields (`source`, `target`, `description`, `expected_effect`) are present, and the “AI-only proposal” constraint is respected.

## 8. Execution & CLI Flow (Sections 12.8–12.12)
- ✅ The CLI sequence shows how to register capabilities, validate intents, compose, run, inspect traces/violations, and submit patches, aligning with Section 11. This confirms the described artifacts are accessible through a CLI surface, provided the `tm` commands exist.
- ⚠️ The “tm compose --intent intent.yaml --policy policy.yaml” command assumes a composer that understands intents/policies; since the repo currently lacks Intent/Capability artifacts (see `spec-to-code-map.md`), the CLI surface cannot be implemented yet.

## Summary of Gaps
1. **IntentSpec must declare `version` + `context_refs`, and the constraint must reference a named policy invariant.** Otherwise, the composer cannot correlate the intent with the policy graph.
2. **PolicySpec needs `policy_id`, `version`, and guard metadata; the guard mentioned in the workflow is unspecified.** Without those, the workflow cannot be encoded as an artifact or enforced by runtime guard machinery.
3. **WorkflowPolicy candidates must be represented as full artifacts (steps, explanations, guard attachments) instead of plain capability lists.** The Reference Workflow currently stops at prose.
4. **PatchProposal must include `proposal_id` and `rationale` to be auditable.**
5. **The violation report must refer to a named invariant (`policy.invariant.no_unvalidated_external_write`) to satisfy the schema.**
6. **Execution traces should at least include run identifiers/timestamps for deterministic auditing.**

## Recommendations before Phase 0 acceptance
- Extend the reference artifacts to include the missing fields listed above, ensuring every step can be reified as schemaful YAML/JSON.
- Define a guard artifact (policy guard or workflow guard) and show how it enrolls `external.write` in the approved workflow.
- Provide an explicit `WorkflowPolicy` structure (with step IDs, transitions, guard associations, and explanations) so the composer/verification/ runtime chain can operate on real artifacts.
