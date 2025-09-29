# Contributing

## Dev setup
- Python 3.11+
- `pytest -q`
- Ensure repo root is on `PYTHONPATH` (pytest.ini or env var)

## Branching
- Feature branches like `feat/<area>-<slug>`

## Commits
- Conventional Commits:
  - `feat(ai): add llm client`
  - `feat(steps): add ai.llm_call`
  - `docs: add policy adapter how-to`

## Tests
- Add tests under `tests/` for new modules; avoid modifying legacy tests.
