# Runtime Overview

- Steps (`tm/steps/...`) execute units of work; each step returns a normalized dict.
- LLM client (`tm/ai/...`) is provider-agnostic and async.
- Policy layer (`tm/policy/...`) supplies tunables to steps or flows.
- Recorder bridge avoids hard deps on core recorder; failures are non-fatal.
