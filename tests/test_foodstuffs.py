"""Offline tests for Foodstuffs price parsing and department skip lists."""

from nzgrocery.foodstuffs import (
    DEPARTMENTS,
    FINGERPRINT_USER,
    HITS_PER_PAGE,
    PAGE_GAP_SECONDS,
    matching_tree,
    money_from_cents,
    price_per_text,
    product_url,
    promo_bits,
    row_from_product,
    search_body,
    store_from_api,
)

WEB = "https://www.paknsave.co.nz"
WHEN = "2026-10-12T09:00:00+13:00"


def _row(product, department="produce"):
    return row_from_product(
        product,
        "PAK'nSAVE Albany",
        WHEN,
        WEB,
        "pns",
        DEPARTMENTS[department],
        chain="paknsave",
        store_id="65defcf2-bc15-490e-a84f-1f13b769cd22",
        department_name=department,
    )


def test_money_from_cents():
    assert money_from_cents(349) == 3.49
    assert money_from_cents("199") == 1.99
    assert money_from_cents(0) == 0.0
    assert money_from_cents(None) is None
    assert money_from_cents("nope") is None


def test_delay_and_fingerprint_are_unchanged():
    assert PAGE_GAP_SECONDS == (2.0, 4.0)
    assert HITS_PER_PAGE == 40
    assert FINGERPRINT_USER == "nz-grocery-prices"


def test_department_skip_lists():
    assert DEPARTMENTS["produce"]["root"] == "Fruit & Vegetables"
    assert DEPARTMENTS["produce"]["skip_level1"] == set()
    assert DEPARTMENTS["produce"]["skip_level2"] == {"Salad Toppers & Dressings"}
    assert DEPARTMENTS["meat"]["root"] == "Meat, Poultry & Seafood"
    assert DEPARTMENTS["meat"]["skip_level1"] == {
        "Deli Meats",
        "Deli Meats & Smoked Fish",
        "Plant Based Alternatives",
        "Makeaways",
        "Dairy Free & Meat Free",
    }
    assert "Ham & Pork Slices" in DEPARTMENTS["meat"]["skip_level2"]
    assert "Plant Based Sausages & Patties" in DEPARTMENTS["meat"]["skip_level2"]
    assert "Fridge, Deli & Eggs" in DEPARTMENTS["meat"]["skip_level2"]


def test_price_promos_and_comparative_price():
    product = {
        "productId": "5033714-EA-000",
        "name": "  Bananas  ",
        "displayName": "kg",
        "singlePrice": {
            "price": 349,
            "comparativePrice": {"pricePerUnit": 349, "measureDescription": "1kg"},
        },
        "promotions": [
            {
                "rewardType": "NEW_PRICE",
                "threshold": 2,
                "rewardValue": 500,
                "cardDependencyFlag": True,
                "description": "not used for NEW_PRICE",
            },
            {
                "rewardType": "OTHER",
                "description": "Extra Low",
                "cardDependencyFlag": True,
            },
        ],
        "categoryTrees": [
            {"level0": "Fruit & Vegetables", "level1": "Fruit", "level2": "Bananas"},
        ],
    }
    row = _row(product)
    assert row["price_nzd"] == 3.49
    assert row["unit_or_size"] == "kg"
    assert row["price_per"] == "$3.49 / 1kg"
    assert row["raw_price_text"] == "$3.49; 2 for $5.00; Clubcard; Extra Low"
    assert row["name"] == "Bananas"
    assert row["department"] == "produce"
    assert row["category"] == "Fruit & Vegetables / Fruit / Bananas"
    assert row["chain"] == "paknsave"
    assert row["product_url"] == f"{WEB}/shop/product/5033714_ea_000pns"
    assert promo_bits(product) == ["2 for $5.00", "Clubcard", "Extra Low"]


def test_each_unit_and_promo_comparative_fallback():
    product = {
        "productId": "already_pns",
        "name": "Lemon",
        "displayName": "EA",
        "singlePrice": {"price": 80},
        "promotions": [
            {
                "description": "Special",
                "comparativePrice": {"pricePerUnit": 100, "unitQuantityUom": "ea"},
            }
        ],
        "categoryTrees": [
            {"level0": "Fruit & Vegetables", "level1": "Fruit", "level2": "Lemons"},
        ],
    }
    row = _row(product)
    assert row["unit_or_size"] == "each"
    assert row["price_per"] == "$1.00 / each"
    assert price_per_text(product) == "$1.00 / each"
    assert row["product_url"].endswith("/already_pns")
    assert row["raw_price_text"] == "$0.80; Special"


def test_bare_price_fallback_and_missing_price():
    kept = _row(
        {
            "name": "Loose apples",
            "price": 250,
            "categoryTrees": [{"level0": "Fruit & Vegetables", "level1": "Fruit"}],
        }
    )
    assert kept["price_nzd"] == 2.5
    assert kept["product_id"] is None
    assert kept["product_url"] is None
    dropped = _row(
        {
            "name": "No price",
            "categoryTrees": [{"level0": "Fruit & Vegetables", "level1": "Fruit", "level2": "Apples"}],
        }
    )
    assert dropped is None


def test_produce_skips_salad_toppers_and_prefers_a_real_level2():
    only_toppers = {
        "productId": "1",
        "name": "Salad crunch",
        "singlePrice": {"price": 300},
        "displayName": "each",
        "categoryTrees": [
            {
                "level0": "Fruit & Vegetables",
                "level1": "Salads",
                "level2": "Salad Toppers & Dressings",
            }
        ],
    }
    assert matching_tree(only_toppers, DEPARTMENTS["produce"]) is None
    assert _row(only_toppers) is None

    both = {
        "productId": "2",
        "name": "Cos lettuce",
        "singlePrice": {"price": 300},
        "displayName": "each",
        "categoryTrees": [
            {"level0": "Fruit & Vegetables", "level1": "Vegetables"},
            {
                "level0": "Fruit & Vegetables",
                "level1": "Salads",
                "level2": "Salad Toppers & Dressings",
            },
            {"level0": "Fruit & Vegetables", "level1": "Vegetables", "level2": "Lettuce"},
            {"level0": "Pantry", "level1": "Dressings", "level2": "Salad Toppers & Dressings"},
        ],
    }
    row = _row(both)
    assert row["category"] == "Fruit & Vegetables / Vegetables / Lettuce"


def test_meat_skip_lists():
    deli = {
        "productId": "d1",
        "name": "Champagne ham",
        "singlePrice": {"price": 500},
        "displayName": "kg",
        "categoryTrees": [
            {"level0": "Meat, Poultry & Seafood", "level1": "Deli Meats", "level2": "Ham"},
        ],
    }
    assert _row(deli, "meat") is None
    plant = {
        "productId": "p1",
        "name": "Veggie sausage",
        "singlePrice": {"price": 800},
        "categoryTrees": [
            {
                "level0": "Meat, Poultry & Seafood",
                "level1": "Free Range",
                "level2": "Plant Based Sausages & Patties",
            }
        ],
    }
    assert _row(plant, "meat") is None
    pets = {
        "productId": "pet",
        "name": "Dog roll",
        "singlePrice": {"price": 400},
        "categoryTrees": [{"level0": "Pets", "level1": "Dog", "level2": "Rolls"}],
    }
    assert _row(pets, "meat") is None
    beef = {
        "productId": "b1-KG-000",
        "name": "Beef mince",
        "singlePrice": {"price": 1699},
        "displayName": "kg",
        "categoryTrees": [
            {
                "level0": "Meat, Poultry & Seafood",
                "level1": "Beef",
                "level2": "Mince",
            }
        ],
    }
    row = _row(beef, "meat")
    assert row["department"] == "meat"
    assert row["price_nzd"] == 16.99
    assert row["category"] == "Meat, Poultry & Seafood / Beef / Mince"
    assert row["product_url"].endswith("/b1_kg_000pns")


def test_search_body_and_product_url():
    body = search_body("store-1", 3, "Meat, Poultry & Seafood")
    assert body["page"] == 3
    assert body["hitsPerPage"] == 40
    assert body["storeId"] == "store-1"
    assert body["sortOrder"] == "NI_POPULARITY_ASC"
    assert body["tobaccoQuery"] is False
    assert body["precisionMedia"]["disableAds"] is True
    filters = body["algoliaQuery"]["filters"]
    assert filters == 'stores:store-1 AND category0NI:"Meat, Poultry & Seafood"'
    assert product_url("ABC-1", "https://www.newworld.co.nz", "nw") == (
        "https://www.newworld.co.nz/shop/product/abc_1nw"
    )


def test_store_from_api_maps_physical_address():
    store = store_from_api(
        {
            "id": "002b83de-b79d-4228-a787-bd0765b6cb56",
            "name": "PAKnSAVE Wairau Road",
            "address": "30 Wairau Road, Wairau Valley, Auckland, 0627",
            "latitude": -36.778705,
            "longitude": 174.744295,
            "clickAndCollect": True,
            "delivery": False,
            "onlineActive": True,
            "physicalAddress": {
                "streetName": "30 Wairau Road",
                "cityName": "Auckland",
                "additionalCityName": "Wairau Valley",
                "regionName": "Auckland",
                "postalCode": "0627",
            },
            "phone": "should not be copied",
        },
        "paknsave",
    )
    assert store.chain == "paknsave"
    assert store.id == "002b83de-b79d-4228-a787-bd0765b6cb56"
    assert store.name == "PAKnSAVE Wairau Road"
    assert store.suburb == "Wairau Valley"
    assert store.region == "Auckland"
    assert store.postcode == "0627"
    assert store.latitude == -36.778705
    assert store.extra == {
        "clickAndCollect": True,
        "delivery": False,
        "onlineActive": True,
        "city": "Auckland",
    }
    assert "phone" not in store.extra
