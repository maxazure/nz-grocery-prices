"""Offline tests for the reference-data cache."""

from __future__ import annotations

import json
from datetime import timedelta

from nzgrocery.cache import now_nz
from nzgrocery.cli import main
from nzgrocery.models import Store
from nzgrocery.reference import (
    load_categories,
    load_or_fetch_categories,
    load_or_fetch_store_payload,
    load_store_payload,
    reference_status,
    save_store_payload,
    ttl_days,
)


def test_ttl_constants_and_env_override(monkeypatch):
    assert ttl_days("stores") == 7
    assert ttl_days("categories") == 7
    monkeypatch.setenv("NZGROCERY_REFERENCE_TTL_DAYS", "3")
    assert ttl_days("stores") == 3
    monkeypatch.setenv("NZGROCERY_REFERENCE_TTL_DAYS", "0")
    assert ttl_days("categories") == 0


def test_fresh_store_list_is_reused_without_network():
    save_store_payload("paknsave", {"stores": [{"id": "cached"}]})

    def fetch():
        raise AssertionError("network")

    payload = load_or_fetch_store_payload("paknsave", fetch)
    assert payload == {"stores": [{"id": "cached"}]}
    assert load_store_payload("paknsave")["stores"][0]["id"] == "cached"


def test_expired_store_list_is_refetched():
    stale = (now_nz() - timedelta(days=8)).isoformat(timespec="seconds")
    save_store_payload("newworld", {"stores": [{"id": "old"}]}, fetched_at=stale)
    calls = []

    def fetch():
        calls.append("network")
        return {"stores": [{"id": "new"}]}

    payload = load_or_fetch_store_payload("newworld", fetch)
    assert calls == ["network"]
    assert payload["stores"][0]["id"] == "new"
    assert load_store_payload("newworld")["stores"][0]["id"] == "new"


def test_force_refetches_a_fresh_store_list():
    save_store_payload("newworld", {"storeAreas": []})
    calls = []

    def fetch():
        calls.append("network")
        return {"storeAreas": [{"name": "Canterbury"}]}

    payload = load_or_fetch_store_payload("newworld", fetch, force=True)
    assert calls == ["network"]
    assert payload["storeAreas"][0]["name"] == "Canterbury"


def test_categories_follow_the_same_ttl():
    from nzgrocery.reference import save_categories

    save_categories("paknsave", {"facets": {"Fruit & Vegetables": {"category1NI": ["Fruit"]}}})

    def fetch():
        raise AssertionError("network")

    loaded = load_or_fetch_categories("paknsave", fetch)
    assert "Fruit & Vegetables" in loaded["facets"]
    stale = (now_nz() - timedelta(days=8)).isoformat(timespec="seconds")
    save_categories("paknsave", {"facets": {}}, fetched_at=stale)
    assert load_categories("paknsave") is None


def test_stores_live_reuses_cache_and_no_cache_refetches(monkeypatch, capsys):
    save_store_payload(
        "paknsave",
        {
            "stores": [
                {
                    "id": "store-1",
                    "name": "PAK'nSAVE Cached",
                    "address": "1 Main Road, Timaru",
                    "physicalAddress": {
                        "cityName": "Timaru",
                        "regionName": "Canterbury",
                        "postalCode": "7910",
                    },
                }
            ]
        },
    )

    def boom(self):
        raise AssertionError("network")

    monkeypatch.setattr("nzgrocery.foodstuffs.FoodstuffsClient.fetch_store_payload_network", boom)
    assert main(["stores", "--live", "--chain", "paknsave", "--region", "canterbury", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["name"] == "PAK'nSAVE Cached"
    assert payload[0]["region"] == "Canterbury"

    def refreshed(self):
        return {
            "stores": [
                {
                    "id": "store-2",
                    "name": "PAK'nSAVE Refreshed",
                    "address": "2 Main Road, Timaru",
                    "physicalAddress": {"cityName": "Timaru", "regionName": "Canterbury"},
                }
            ]
        }

    monkeypatch.setattr("nzgrocery.foodstuffs.FoodstuffsClient.fetch_store_payload_network", refreshed)
    assert main(["stores", "--live", "--chain", "paknsave", "--no-cache", "--json"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again[0]["id"] == "store-2"


def test_status_json_includes_reference_caches(capsys):
    save_store_payload("newworld", {"storeAreas": []})
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["snapshots"] == []
    row = next(item for item in payload["reference"] if item["kind"] == "stores")
    assert row["chain"] == "newworld"
    assert row["expired"] is False
    assert row["ttl"] == 7
    assert isinstance(row["age"], int)
    assert row["fetched_at"]
    assert row["file"].endswith("stores-newworld.json")


def test_reference_status_marks_expired_files():
    stale = (now_nz() - timedelta(days=8)).isoformat(timespec="seconds")
    save_store_payload("paknsave", {"stores": []}, fetched_at=stale)
    match = next(row for row in reference_status() if row["kind"] == "stores")
    assert match["expired"] is True
    assert match["ttl"] == 7
    assert match["age"] > 7 * 86400
