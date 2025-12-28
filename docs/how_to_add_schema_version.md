# How to Add or Update an Artifact Schema Version

When the v0 artifacts need schema changes (new metadata, extra fields, or revised plan rule checks), follow these steps:

1. **Update `TM-SPEC-ARTIFACTS-V0.md`** so the canonical form and gap/policy requirements reflect the new fields. Keep the spec minimal but explicit about invariants (Candidate vs Accepted, hashing, verifier expectations).
2. **Extend the model and schema definitions**:
   - If you add fields, ensure `tm/artifacts/models.py` accepts them (plan steps/rules, trace links, etc.) and expose them via the dataclasses.
   - Update the JSON Schema in `tm/artifacts/schemas/v0/*.json` so validators and CLI tooling know about the new structure.
3. **Adjust `tm/artifacts/verify.py` and consistency rules** (C1/C2/C3) to handle any new invariants or metadata you now track (e.g., new derived-from fields or invariant statuses).
4. **Add tests**: `tests/test_verifier_v0.py`, `tests/test_consistency_v0.py`, and the golden suite under `tests/golden/` must cover the updated schema. Golden tests anchor on deterministic `body_hash` values—update them when canonical normalization legitimately changes.
5. **Sync CLI behavior**: If the new schema introduces command-line inputs (e.g., new plan lint constraints), update `tm/cli/artifacts_cli.py` and `tm/lint/plan_lint.py` accordingly, plus `docs/artifacts_cli.md` to document new commands or flags.
6. **Propagate to CI**: Ensure `.github/workflows/artifacts.yml` still runs your new checks, and update `scripts/ci_check_artifacts.sh` so the artifacts pipeline exercises the changes.

Finally, re-run the golden verification script and relevant tests to capture the new `body_hash` values before merging.
