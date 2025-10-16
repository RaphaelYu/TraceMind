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
