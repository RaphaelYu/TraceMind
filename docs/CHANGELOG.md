# Changelog

## [Unreleased]
- _None_

## [1.1.0] - 2025-10-13
- Add: trigger runtime (cron/webhook/filesystem adapters, `tm triggers run`, queue dispatcher)
- Add: daemon integration for triggers (`tm daemon start --enable-triggers`, consolidated `tm.daemon.run` entrypoint)
- Add: trigger configuration tooling (`tm triggers init|validate`, `templates/triggers.yaml`, `docs/triggers.md`)
- Update: README / daemon docs / smoke script with trigger workflows
- Fix: Windows filesystem trigger config parsing by switching tests to JSON generation
- Bump: project version to 1.1.0
