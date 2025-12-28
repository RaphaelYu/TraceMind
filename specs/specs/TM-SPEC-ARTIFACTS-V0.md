# TM-SPEC-ARTIFACTS-V0

## Status definitions
- **Candidate**: A preliminary artifact that may change before acceptance. Candidates can be submitted by any producer. They must include all envelope metadata but may still be under review, missing approvals, or pending canonicalization.
- **Accepted**: A Candidate that has passed all required validations, hashing comparisons, and policy checks. Accepted artifacts are immutable, versioned, and can be referenced by downstream systems.

## Artifact envelope
Each artifact is a document composed of an `envelope` and a `body`. The envelope contains metadata required for identification, routing, and verification:

| Field | Description |
| --- | --- |
| `artifact_id` (string) | Stable identifier, e.g., `tm-artifact-<uuid>` or `<intent_id>-v<major>`.
| `status` (enum) | One of `candidate` or `accepted`.
| `version` (semver) | Indicates the artifact schema version (e.g., `v0.1`).
| `created_by` (string) | Originating agent or service ID.
| `created_at` (ISO 8601) | Timestamp in UTC when artifact was produced.
| `body_hash` (hex string) | SHA-256 over the canonicalized `body` defined below.
| `envelope_hash` (hex string) | SHA-256 over the canonicalized envelope fields excluding `envelope_hash` itself.
| `signature` (optional string) | Optional armored signature of `envelope_hash` when policies require.
| `meta` (map) | Arbitrary key/value flags (publish, environment, etc.)

## Normal form rules
1. Serialize both `envelope` (minus `envelope_hash`) and `body` using canonical JSON:
   - Stable key ordering (lexicographic).
   - No insignificant whitespace.
   - Arrays preserve insertion order.
   - Booleans, numbers, and null use native JSON representations.
2. Before hashing apply:
   - Remove trailing comments or metadata not present in schema.
   - Normalize timestamps to UTC RFC 3339.
   - For maps with optional fields, keep absent rather than null.
3. The canonical bytes are the UTF-8 encoded JSON string produced by the steps above.

## Hashing rules
- Compute `body_hash` = `SHA-256(canonical_body_bytes)`.
- Compute `envelope_hash` = `SHA-256(canonical_envelope_bytes)`.
- `canonical_envelope_bytes` must include `body_hash` so traceability anchors on the latest body state.
- Hash outputs are lowercase hex strings and stored in the envelope. Any change to metadata or body invalidates the artifact until rehashed.

## Verifier invariants
1. Envelope fields `artifact_id`, `status`, `version`, `created_by`, `created_at`, `body_hash`, and `envelope_hash` must exist for every artifact.
2. `status` must be `accepted` only if:
   - `body_hash` matches the canonicalized body.
   - `envelope_hash` matches the canonicalized envelope computed after `body_hash` is set.
   - Optional `signature`, if present, verifies against a configured key.
3. Candidates are allowed to have placeholder `signature` and may omit certain policy metadata, but validators must flag them for manual review if missing.
4. Hash comparisons must use constant-time digest equality when implemented to prevent timing leaks.
5. `version` must align with supported schema releases; mismatched versions must trigger upgrade or rejection.

## Body schemas
### Candidate body (minimally required fields)
```yaml
- type: string            # e.g., "intent", "asset", "decision"
- payload:
    data: map             # opaque content specific to artifact type
    references: []        # list of artifact_id strings this candidate scoped to
- annotations: map         # producer notes, validation flags, etc.
```

### Accepted body (adds hardened requirements)
```yaml
- type: string
- payload:
    data: map
    references: []
- annotations:
    review_status: string  # e.g., "approved", "auto"
    verifier: string       # component that accepted the artifact
    policy_checks: []      # list of policy identifiers applied
- resolved_at: ISO 8601     # timestamp when acceptance occurred
```

## Path forward
- Producers should emit Candidate artifacts, compute canonical hashes immediately, and attach metadata describable by the envelope schema.
- The verifier compares hashes, applies policy checks, and then re-serializes to produce an Accepted artifact with a new `version` or `resolved_at`.
