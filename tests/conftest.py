"""Keep unit tests away from the real home-directory cache."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_nzgrocery_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("NZGROCERY_DB", str(tmp_path / "nzgrocery-home" / "prices.sqlite"))
    monkeypatch.delenv("NZGROCERY_DATA", raising=False)
    monkeypatch.delenv("NZGROCERY_MIN_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("NZGROCERY_REFERENCE_TTL_DAYS", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
