"""PAK'nSAVE and New World guest catalogue HTTP client.

Uses public website guest credentials and production catalogue endpoints.
No browser, login, cart or stored credentials. Requests stay 2–4 seconds apart.
"""

from __future__ import annotations

import time
import json
import urllib.request
import urllib.error
import random
import sys
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from nzgrocery.errors import Blocked, NoRows, StoreNotFound, StoreVerificationError
from nzgrocery.models import Store
from nzgrocery.stores import find_store_locally, match_store, normalise_name

TZ = ZoneInfo("Pacific/Auckland")
FINGERPRINT_USER = "nz-grocery-prices"

# category0NI values read from the guest catalogue facets (Pak'nSave Albany,
# 2026-10-04). Do not rename these; they are the API's own labels.
DEPARTMENTS = {
    "produce": {
        "root": "Fruit & Vegetables",
        "skip_level1": set(),
        "skip_level2": {"Salad Toppers & Dressings"},
    },
    # Subcategory skips are category1NI / category2NI labels from the same
    # facet response under "Meat, Poultry & Seafood": deli, plant-based,
    # and hot-counter / ready-to-eat items. Pets and the Frozen aisle are
    # different category0NI values, so the root filter already excludes them.
    "meat": {
        "root": "Meat, Poultry & Seafood",
        "skip_level1": {
            "Deli Meats",
            "Deli Meats & Smoked Fish",
            "Plant Based Alternatives",
            "Makeaways",
            "Dairy Free & Meat Free",
        },
        "skip_level2": {
            "Ham & Pork Slices",
            "Salami & Cured Meats",
            "Smoked Salmon & Fish",
            "Pre-Cooked Sausages",
            "Breakfast Bacon and Egg Muffin",
            "Chicken Burger Bacon Stack",
            "Cheesy Taco Wrap",
            "Meatball Sub Sandwich",
            "Vegetarian Meat & Falafel",
            "Chicken & Mince Alternatives",
            "Plant Based Sausages & Patties",
            "Fridge, Deli & Eggs",
        },
    },
}
HITS_PER_PAGE = 40
MAX_PAGES = 20
PAGE_GAP_SECONDS = (2.0, 4.0)

BANNERS = {
    "paknsave": {
        "web": "https://www.paknsave.co.nz",
        "api": "https://api-prod.paknsave.co.nz/v1/edge",
        "url_suffix": "pns",
    },
    "newworld": {
        "web": "https://www.newworld.co.nz",
        "api": "https://api-prod.newworld.co.nz/v1/edge",
        "url_suffix": "nw",
    },
}

def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def money_from_cents(cents) -> float | None:
    if cents is None:
        return None
    try:
        return round(int(cents) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def format_nzd(amount: float) -> str:
    return f"${amount:.2f}"


def unit_label(display_name: str | None) -> str | None:
    if not display_name:
        return None
    text = display_name.strip()
    if text.lower() in {"ea", "each"}:
        return "each"
    return text


def comparative_text(node: dict | None) -> str | None:
    if not isinstance(node, dict):
        return None
    amount = money_from_cents(node.get("pricePerUnit"))
    if amount is None:
        return None
    unit = node.get("measureDescription") or node.get("unitQuantityUom") or ""
    unit = str(unit).strip()
    if unit.lower() == "ea":
        unit = "each"
    return f"{format_nzd(amount)} / {unit}" if unit else format_nzd(amount)


def price_per_text(product: dict) -> str | None:
    single = product.get("singlePrice") or {}
    text = comparative_text(single.get("comparativePrice"))
    if text:
        return text
    for promo in product.get("promotions") or []:
        if isinstance(promo, dict):
            text = comparative_text(promo.get("comparativePrice"))
            if text:
                return text
    return None


def promo_bits(product: dict) -> list[str]:
    bits: list[str] = []
    for promo in product.get("promotions") or []:
        if not isinstance(promo, dict):
            continue
        reward = promo.get("rewardValue")
        threshold = promo.get("threshold")
        reward_type = promo.get("rewardType")
        if reward_type == "NEW_PRICE" and threshold and reward is not None:
            amount = money_from_cents(reward)
            if amount is not None:
                bits.append(f"{threshold} for {format_nzd(amount)}")
        elif promo.get("description"):
            bits.append(str(promo["description"]))
        if promo.get("cardDependencyFlag"):
            bits.append("Clubcard")
    seen = set()
    out = []
    for bit in bits:
        if bit not in seen:
            seen.add(bit)
            out.append(bit)
    return out


def matching_tree(product: dict, department: dict) -> dict | None:
    """First category tree under the department root that is not skipped."""
    chosen = None
    for tree in product.get("categoryTrees") or []:
        if not isinstance(tree, dict):
            continue
        if tree.get("level0") != department["root"]:
            continue
        if tree.get("level1") in department["skip_level1"]:
            continue
        if tree.get("level2") in department["skip_level2"]:
            continue
        if chosen is None or (tree.get("level2") and not chosen.get("level2")):
            chosen = tree
    return chosen


def category_label(tree: dict) -> str:
    parts = [tree.get("level0"), tree.get("level1"), tree.get("level2")]
    return " / ".join(str(part) for part in parts if part)


def product_url(product_id: str, web: str, suffix: str) -> str:
    slug = product_id.strip().lower().replace("-", "_")
    if not slug.endswith(suffix):
        slug += suffix
    return f"{web}/shop/product/{slug}"


def shelf_price(product: dict) -> float | None:
    single = product.get("singlePrice") or {}
    amount = money_from_cents(single.get("price"))
    if amount is not None:
        return amount
    if "price" in product and "singlePrice" not in product:
        return money_from_cents(product.get("price"))
    return None


def row_from_product(
    product: dict,
    store_name: str,
    fetched_at: str,
    web: str,
    suffix: str,
    department: dict,
    *,
    chain: str,
    store_id: str,
    department_name: str,
) -> dict | None:
    tree = matching_tree(product, department)
    if tree is None:
        return None
    name = (product.get("name") or "").strip()
    product_id = (product.get("productId") or "").strip()
    price = shelf_price(product)
    if not name or price is None:
        return None
    raw_bits = [format_nzd(price)]
    raw_bits.extend(promo_bits(product))
    return {
        "fetched_at": fetched_at,
        "chain": chain,
        "store_id": store_id,
        "store": store_name,
        "department": department_name,
        "category": category_label(tree),
        "name": name,
        "price_nzd": price,
        "unit_or_size": unit_label(product.get("displayName")),
        "price_per": price_per_text(product),
        "product_url": product_url(product_id, web, suffix) if product_id else None,
        "raw_price_text": "; ".join(raw_bits),
        "product_id": product_id or None,
    }


def search_body(store_id: str, page: int, category_root: str) -> dict:
    filters = f'stores:{store_id} AND category0NI:"{category_root}"'
    return {
        "algoliaQuery": {
            "attributesToHighlight": [],
            "attributesToRetrieve": [
                "productID",
                "Type",
                "sponsored",
                "category0NI",
                "category1NI",
                "category2NI",
            ],
            "facets": ["category0NI", "category1NI"],
            "filters": filters,
            "highlightPostTag": "__/ais-highlight__",
            "highlightPreTag": "__ais-highlight__",
            "hitsPerPage": HITS_PER_PAGE,
            "maxValuesPerFacet": 20,
            "page": page,
            "query": "",
            "analyticsTags": ["fs#WEB:desktop"],
        },
        "algoliaFacetQueries": [],
        "storeId": store_id,
        "hitsPerPage": HITS_PER_PAGE,
        "page": page,
        "sortOrder": "NI_POPULARITY_ASC",
        "tobaccoQuery": False,
        "precisionMedia": {
            "adDomain": "CATEGORY_PAGE",
            "adPositions": [],
            "publishImpressionEvent": False,
            "disableAds": True,
        },
    }


def store_from_api(raw: dict, chain: str) -> Store:
    """Map one Foodstuffs ``/store`` object onto :class:`Store`."""
    physical = raw.get("physicalAddress") or {}
    suburb = physical.get("additionalCityName") or physical.get("cityName")
    extra = {
        "clickAndCollect": raw.get("clickAndCollect"),
        "delivery": raw.get("delivery"),
        "onlineActive": raw.get("onlineActive"),
    }
    city = physical.get("cityName")
    if city:
        extra["city"] = str(city).strip()
    if raw.get("banner"):
        extra["banner"] = raw.get("banner")
    return Store(
        chain=chain,
        id=str(raw["id"]),
        name=str(raw.get("name") or "").strip(),
        address=str(raw.get("address") or "").strip(),
        suburb=str(suburb).strip() if suburb else None,
        region=physical.get("regionName"),
        postcode=str(physical["postalCode"]) if physical.get("postalCode") else None,
        latitude=raw.get("latitude"),
        longitude=raw.get("longitude"),
        extra=extra,
    )


def stores_from_payload(
    payload: dict,
    chain: str,
    *,
    region_name: str | None = None,
) -> list[Store]:
    stores: list[Store] = []
    for raw in payload.get("stores") or []:
        if not isinstance(raw, dict) or raw.get("id") is None:
            continue
        if region_name is not None:
            region = str((raw.get("physicalAddress") or {}).get("regionName") or "")
            if region != region_name:
                continue
        stores.append(store_from_api(raw, chain))
    return stores


def _facet_snapshot(payload: dict) -> dict | None:
    """Facet or category-tree fragment from a product search, without the products."""
    if not isinstance(payload, dict):
        return None
    found = {}
    for key in ("facets", "algoliaFacets", "facetCounts", "categoryFacets"):
        value = payload.get(key)
        if value:
            found[key] = value
    return found or None


def level1_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        parts = (row.get("category") or "").split(" / ")
        if len(parts) > 1:
            counts[parts[1]] = counts.get(parts[1], 0) + 1
    return counts


def department_keys(department: str) -> list[str]:
    if department == "all":
        return ["produce", "meat"]
    if department not in DEPARTMENTS:
        known = ", ".join(["produce", "meat", "all"])
        raise ValueError(f"unknown department {department!r}; expected one of {known}")
    return [department]


def pause() -> None:
    delay = random.uniform(*PAGE_GAP_SECONDS)
    eprint(f"waiting {delay:.1f}s")
    time.sleep(delay)


def _name_ok(store: Store, query: str) -> bool:
    if store.id.casefold() == query.strip().casefold():
        return True
    return normalise_name(query) in normalise_name(store.name)


class FoodstuffsClient:
    """Guest client for one Foodstuffs banner (``paknsave`` or ``newworld``)."""

    def __init__(self, banner: str, *, verbose: bool = False) -> None:
        key = banner.strip().lower()
        if key not in BANNERS:
            raise ValueError(f"unknown banner {banner!r}; expected one of {sorted(BANNERS)}")
        self.banner = key
        self.verbose = verbose
        self.spec = BANNERS[key]

    def list_stores(self, *, force: bool = False) -> list[Store]:
        payload = self.fetch_store_payload(force=force)
        return stores_from_payload(payload, self.banner)

    def fetch_store_payload(self, *, force: bool = False) -> dict:
        from nzgrocery.reference import load_or_fetch_store_payload

        def fetch() -> dict:
            return self.fetch_store_payload_network()

        return load_or_fetch_store_payload(self.banner, fetch, force=force)

    def fetch_store_payload_network(self) -> dict:
        return self._fetch_store_payload()

    def fetch(self, store_query: str, department: str) -> tuple[Store, list[dict]]:
        return self._fetch(store_query, department)

    def _fetch_store_payload(self) -> dict:
        with self._session() as headers:
            pause()
            return request_json(f"{self.spec['api']}/store", headers)

    def _fetch(self, store_query: str, department: str) -> tuple[Store, list[dict]]:
        from nzgrocery.reference import load_categories, save_categories, save_store_payload

        keys = department_keys(department)
        try:
            chosen = find_store_locally(self.banner, store_query)
        except StoreNotFound:
            chosen = None
        categories_were_fresh = load_categories(self.banner) is not None
        observed_facets: dict[str, dict] = {}
        with self._session() as headers:
            if chosen is None:
                pause()
                payload = request_json(f"{self.spec['api']}/store", headers)
                save_store_payload(self.banner, payload)
                stores = stores_from_payload(payload, self.banner)
                chosen = match_store(stores, store_query)
            if not _name_ok(chosen, store_query):
                raise StoreVerificationError(
                    f"selected store name {chosen.name!r} failed the name check; nothing saved."
                )
            eprint(
                f"selected store {chosen.name!r} id={chosen.id} address={chosen.address!r}"
            )
            fetched_at = now_iso()
            rows: list[dict] = []
            seen: set[str] = set()
            for department_name in keys:
                dept = DEPARTMENTS[department_name]
                page_rows = self._pages(
                    headers,
                    chosen,
                    dept,
                    department_name,
                    fetched_at,
                    observed_facets,
                )
                for record in page_rows:
                    marker = record["product_id"] or (
                        f"{record['name']}|{record['unit_or_size']}|{record['price_nzd']}"
                    )
                    key = f"{department_name}:{marker}"
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(record)
        if observed_facets and not categories_were_fresh:
            save_categories(self.banner, {"facets": observed_facets})
        if not rows:
            raise NoRows(f"no {department} rows parsed; nothing saved.")
        if not _name_ok(chosen, store_query) or any(
            not _name_ok(Store(chosen.chain, chosen.id, row["store"], ""), store_query)
            for row in rows
        ):
            raise StoreVerificationError("refusing to save: a row failed the store name check")
        return chosen, rows

    def _pages(
        self,
        headers: dict,
        store: Store,
        dept: dict,
        department_name: str,
        fetched_at: str,
        observed_facets: dict | None = None,
    ) -> list[dict]:
        rows: list[dict] = []
        total_pages = 1
        page_index = 0
        web = self.spec["web"]
        suffix = self.spec["url_suffix"]
        while page_index < total_pages and page_index < MAX_PAGES:
            pause()
            eprint(f"{department_name} page {page_index + 1}")
            payload = request_json(
                f"{self.spec['api']}/search/paginated/products", headers,
                search_body(store.id, page_index, dept["root"]),
            )
            if observed_facets is not None and dept["root"] not in observed_facets:
                facets = _facet_snapshot(payload)
                if facets:
                    observed_facets[dept["root"]] = facets
            products = payload.get("products")
            if not isinstance(products, list) or any(not isinstance(p, dict) for p in products):
                raise Blocked("unexpected product list; refusing to save an incomplete snapshot")
            try:
                reported_pages = int(payload.get("totalPages") or 1)
            except (TypeError, ValueError):
                raise Blocked("invalid page count; refusing to save an incomplete snapshot") from None
            if reported_pages > MAX_PAGES or reported_pages < 1:
                raise Blocked("page count outside supported limits; nothing saved")
            total_hits = payload.get("totalHits")
            total_pages = reported_pages
            eprint(
                f"  got {len(products)} products "
                f"(totalHits={total_hits}, totalPages={reported_pages})"
            )
            if not products:
                if page_index > 0 or total_hits:
                    raise Blocked("unexpected empty page; refusing to save an incomplete snapshot")
                break
            for product in products:
                record = row_from_product(
                    product,
                    store.name,
                    fetched_at,
                    web,
                    suffix,
                    dept,
                    chain=self.banner,
                    store_id=store.id,
                    department_name=department_name,
                )
                if record is None:
                    continue
                rows.append(record)
            page_index += 1
        return rows

    @contextmanager
    def _session(self):
        web = self.spec["web"]
        headers = {"accept": "application/json", "content-type": "application/json",
                   "user-agent": "nz-grocery-prices/0.1", "origin": web, "referer": web + "/"}
        token = request_json(web + "/api/user/get-current-user", headers, {
            "fingerprintUser": FINGERPRINT_USER, "fingerprintGuest": "nz-grocery-prices/0.1"
        })
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise Blocked("guest credentials unavailable; stop and try again later")
        headers["authorization"] = "Bearer " + access_token
        yield headers


def request_json(url: str, headers: dict, data: dict | None = None) -> dict:
    """One bounded JSON request. Guest credentials stay in memory."""
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise Blocked(f"catalogue HTTP {exc.code}; no automatic retry") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Blocked(f"catalogue connection failed ({type(exc).__name__})") from None
    except (ValueError, UnicodeError):
        raise Blocked("catalogue returned an unexpected non-JSON response") from None
    if not isinstance(payload, dict):
        raise Blocked("catalogue returned an unexpected JSON structure")
    return payload
