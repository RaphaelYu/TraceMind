# ADR-001: Provider-agnostic LLM Client

## Context
We need an async, provider-agnostic LLM client with minimal dependencies.

## Decision
- Introduce `Provider` protocol with `complete(...)`.
- Implement `FakeProvider` (offline) and `OpenAIProvider` (pluggable transport).
- Step `ai.llm_call` composes a prompt, calls client, records usage.

## Consequences
- Zero-conflict to core runtime.
- Easy to test (FakeProvider) and extend (new providers, transports).
