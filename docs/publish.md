# Publishing Guide

This guide summarizes how to build and publish TraceMind packages either on a
local machine or via CI workflows.

## 1. Local Build (online environment)

```bash
python -m pip install -U pip build twine
python -m build
python -m twine check dist/*
```

The commands produce `dist/*.whl` and `dist/*.tar.gz` and validate them with
`twine`. Pair this with `scripts/release_checklist.sh` to capture the package
file listing:

```bash
./scripts/release_checklist.sh
```

## 2. CI Build (offline or reproducible)

Trigger the "Package Check" GitHub Actions workflow. It builds the distribution,
runs `twine check`, and uploads an artifact containing `dist/*` plus
`housekeeping/pkg-contents.txt` for inspection.

## 3. Publishing to TestPyPI or PyPI

### Using API tokens

```bash
# publish to TestPyPI
twine upload --repository testpypi dist/*

# publish to PyPI
twine upload dist/*
```

Configure `~/.pypirc` or pass `TWINE_USERNAME=__token__` and
`TWINE_PASSWORD=<pypi-token>` environment variables.

### Using Trusted Publishing

Alternatively, wire GitHub Actions to PyPI/TestPyPI via Trusted Publishing:

1. Enable "trusted publisher" for the repository in PyPI/TestPyPI.
2. Update the GitHub workflow to use the PyPI publish action (e.g.,
   `pypa/gh-action-pypi-publish@release/v1`).
3. Run the workflow from a tagged release; PyPI validates the GitHub OIDC token
   and accepts the upload without storing credentials.

Keep the `Package Check` workflow green before pushing to TestPyPI or PyPI.
