## Kripke semantics for TraceMind pipelines

This verifier treats a `Plan` from `tm.pipeline.engine` as a Kripke structure and explores it with bounded BFS.

- **State**: `(store, pending, done, events)` where `store` is a key→value dict, `pending` is the queue of step names, `done` tracks which steps have been executed at least once, and `events` records executed steps. A state is *terminal* when no enabled successors exist.
- **Enabled step**: a pending step whose `reads` are all present in `store`. Executing a step removes one pending instance, marks it as `done`, writes its `writes` keys into the store, appends an event, and enqueues any rule steps whose trigger selectors match the newly written paths. Multiple enabled steps branch nondeterministically.
- **Hash modes**: `full` hashes store + pending + done + events; `store` hashes only the store (coarser deduplication that merges scheduling variations).
- **Exploration**: breadth‑first up to `--depth N`, deduplicating by the chosen hash. Deadlocks are states with pending work but no enabled successors.
- **Invariants**: boolean formulas over predicates `Has(key)`, `Pending(step)`, `Done(step)`, `Terminal`. They must hold in every reachable state.
- **CTL subset**: `EX`, `EF`, `AF`, `EG`, `AG` plus boolean connectives. Formulas are evaluated on the bounded graph rooted at the initial state, and counterexample paths are reconstructed from BFS predecessors.
- **Limitations**: bounded depth may miss longer counterexamples; coarse `store` hashing may merge states with different queues; step functions are abstracted to read/write effects only.
