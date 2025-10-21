# Changelog

## 1.1.1 (2024-08-02)
- Added WDL/PDL test generation via `tm dsl testgen` with ≥6 coverage cases per workflow
- DSL compiler now emits `out/triggers.yaml` from WDL `triggers:` blocks (validated by `tm triggers validate`)
- Introduced PDL policy evaluator allowing flows to execute compiled policies without Python code
- New DSL docs/script walkthrough covering lint→plan→compile→testgen→run pipeline
- CLI updates: `tm dsl plan` (DOT/JSON), `tm dsl testgen`, richer lint outputs

## 1.1.0 (2024-05-09)
- Added WDL/PDL test generation via `tm dsl testgen` with ≥6 coverage cases per workflow
- DSL compiler now emits `out/triggers.yaml` from WDL `triggers:` blocks (validated by `tm triggers validate`)
- Introduced PDL policy evaluator allowing flows to execute compiled policies without Python code
- New DSL docs/script walkthrough covering lint→plan→compile→testgen→run pipeline
- CLI updates: `tm dsl plan` (DOT/JSON), `tm dsl testgen`, richer lint outputs

## 1.0.0 (2024-05-09)
- Scaffold v2: `tm init` minimal template runnable out-of-box
- Plugin SDK + entry-point loader; example exporter
- `tm plugin verify` minimal conformance
- Quickstart docs link

## 1.2.0 (2024-08-XX)
- Added runtime engine abstraction (PythonEngine + ProcessEngine) with JSON-RPC executor support
- `tm dsl compile --emit-ir` now emits Flow IR + manifest validated via JSON Schema
- Introduced IR runner APIs and CLI (`tm runtime run`, `tm verify online`) for offline/online verification
- Added mock ProcessEngine executor and contract tests for REP v0.1
- Expanded documentation: runtime guide, README updates, architecture refresh
- Added smoke tests covering IR execution via Python and process engines
