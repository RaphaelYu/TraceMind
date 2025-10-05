# Migration Guide

TraceMind 1.0.0 freezes the public CLI and plugin APIs. Review the following updates before upgrading from 0.7.x:

- `tm init --template minimal` now creates runnable projects; remove custom scaffolding scripts if redundant.
- Plugins must implement the new SDK interfaces and register via entry points (`trace_mind.*`).
- Use `tm plugin verify` to validate exporters during rollout.
- Follow the Quickstart guide for updated validation workflows.
