import json
from pathlib import Path
import pytest
from nzgrocery.stores import load_bundled_stores, match_store, AmbiguousStore, StoreNotFound, build_auckland_list, filter_stores
from nzgrocery.models import Store

def test_nationwide_two_chains_and_demo_stores():
    stores = load_bundled_stores()
    assert {s.chain for s in stores} == {"paknsave", "newworld"}
    assert len(stores) == 207
    assert all(s.region for s in stores)
    for chain, name in [("newworld", "Ilam"), ("paknsave", "Riccarton")]:
        chosen = match_store(filter_stores(stores, chain=chain), name)
        assert chosen.region == "Canterbury"
        assert chosen.latitude and chosen.longitude
        assert match_store(stores, chosen.id) == chosen

def test_ambiguous_and_exact_names():
    stores = [Store("newworld", "1", "New World Hamilton", ""), Store("newworld", "2", "New World Hamilton East", "")]
    with pytest.raises(AmbiguousStore): match_store(stores, "Hamilton")
    assert match_store(stores, "New World Hamilton").id == "1"
    with pytest.raises(StoreNotFound): match_store(stores, "missing")

def test_albany_across_chains_and_apostrophes():
    stores = load_bundled_stores()
    with pytest.raises(AmbiguousStore): match_store(stores, "Albany")
    assert match_store(stores, "PAK'nSAVE Wairau Road").id == "002b83de-b79d-4228-a787-bd0765b6cb56"

def test_build_store_list():
    fixtures = Path(__file__).parent / "fixtures"
    stores = build_auckland_list(json.loads((fixtures / "foodstuffs_pns.json").read_text()), json.loads((fixtures / "foodstuffs_nw.json").read_text()))
    assert {s.chain for s in stores} == {"paknsave", "newworld"}
    assert all(s.region == "Auckland" for s in stores)
