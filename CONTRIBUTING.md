# Contributing

Use Python 3.10+ and a virtual environment. Install `.[dev]`, run `pytest -q`, and build/check the wheel and source archive as shown in README.

Keep tests offline. Maintain direct HTTP access, TLS verification, bounded timeouts, sequential 2–4 second request spacing and daily cache reuse. Do not add login, challenge handling or automatic repeated retries. Never commit tokens or live price datasets.

Edit only `skills/nz-grocery-prices/`, then run `python scripts/sync_skills.py --zip`. The discovery copies must stay identical. User-facing terms are prices, query, fetch and cache. Keep README examples and CLI behavior consistent.

Release: run tests, validate the skill, build wheel/source/skill ZIP, inspect their contents, update VALIDATION.md with the actual checks, then publish a GitHub release tag and attach the artifacts. PyPI publishing is not configured.
