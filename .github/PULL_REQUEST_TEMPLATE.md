#### What and why

What the change does, and the issue it addresses (if any).

#### Checks

- [ ] `API_KEY_TRANSLATE=test API_KEY_PROOFREAD=test API_KEY_IMAGES=test python -m pytest -q` passes
- [ ] `ruff check src tests` passes
- [ ] a test for the new behaviour or the fixed bug (`tests/test_<feature>.py`)
- [ ] a prompt change: `app.py eval` before and after, the numbers below
- [ ] documentation (`docs/`, README) and `CHANGELOG.md` updated if behaviour or options changed

See [CONTRIBUTING.md](../CONTRIBUTING.md).
