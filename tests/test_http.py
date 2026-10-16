"""Offline checks for direct HTTP requests and bounded failure behavior."""
import io
import json
import urllib.error
import pytest
from nzgrocery import foodstuffs as fs
from nzgrocery.errors import Blocked
from nzgrocery.stores import find_store_locally


def test_http_post_serializes_payload_and_uses_timeout(monkeypatch):
    calls = []
    def open_request(request, timeout):
        calls.append((request, timeout))
        return io.BytesIO(b'{"products": []}')
    monkeypatch.setattr(fs.urllib.request, "urlopen", open_request)
    assert fs.request_json("https://example.invalid/prices", {"accept": "application/json"}, {"storeId": "test"}) == {"products": []}
    request, timeout = calls[0]
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"storeId": "test"}
    assert timeout == 30


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_http_error_stops_without_retry_or_credential_output(monkeypatch, code):
    calls = []
    def fail(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, code, "sensitive response", {}, None)
    monkeypatch.setattr(fs.urllib.request, "urlopen", fail)
    with pytest.raises(Blocked) as caught:
        fs.request_json("https://example.invalid", {"authorization": "Bearer secret"})
    assert str(code) in str(caught.value)
    assert "secret" not in str(caught.value)
    assert "sensitive" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b'<html>challenge</html>', b'[]'])
def test_unexpected_json_is_reported(monkeypatch, body):
    monkeypatch.setattr(fs.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(body))
    with pytest.raises(Blocked): fs.request_json("https://example.invalid", {})


def test_guest_token_required(monkeypatch):
    monkeypatch.setattr(fs, "request_json", lambda *a: {"transition": True})
    with pytest.raises(Blocked):
        with fs.FoodstuffsClient("newworld")._session():
            pytest.fail("missing credentials must stop")


def test_direct_api_uses_selected_store_on_every_page(monkeypatch):
    calls = []
    store = find_store_locally("newworld", "Ilam")
    def request(url, headers, data=None):
        calls.append((url, dict(headers), data))
        if url.endswith("get-current-user"): return {"access_token": "temporary-token"}
        page = data["page"]
        return {"totalPages": 2, "totalHits": 2, "products": [{
            "productId": str(page), "name": "Broccoli", "displayName": "EA",
            "singlePrice": {"price": 249},
            "categoryTrees": [{"level0": "Fruit & Vegetables", "level1": "Vegetables"}]
        }]}
    monkeypatch.setattr(fs, "request_json", request)
    monkeypatch.setattr(fs, "pause", lambda: None)
    selected, rows = fs.FoodstuffsClient("newworld").fetch("Ilam", "produce")
    assert selected.id == store.id and len(rows) == 2
    assert {row["store_id"] for row in rows} == {store.id}
    assert [call[2]["page"] for call in calls[1:]] == [0, 1]
    for url, headers, data in calls[1:]:
        assert url == "https://api-prod.newworld.co.nz/v1/edge/search/paginated/products"
        assert headers["authorization"] == "Bearer temporary-token"
        assert data["storeId"] == store.id
        assert 'stores:' + store.id in data["algoliaQuery"]["filters"]


def test_incomplete_page_is_not_accepted(monkeypatch):
    def request(url, headers, data=None):
        return {"products": [], "totalPages": 3, "totalHits": 100}
    monkeypatch.setattr(fs, "request_json", request)
    monkeypatch.setattr(fs, "pause", lambda: None)
    with pytest.raises(Blocked):
        fs.FoodstuffsClient("paknsave")._pages({}, find_store_locally("paknsave", "Riccarton"), fs.DEPARTMENTS["produce"], "produce", fs.now_iso())
