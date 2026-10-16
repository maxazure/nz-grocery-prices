"""Bundled New Zealand stores and store-query matching.

``build_store_list`` turns the two live catalogue payloads into the
nationwide file. ``build_auckland_list`` is that list filtered to Auckland.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from nzgrocery.errors import AmbiguousStore, StoreNotFound
from nzgrocery.models import CHAIN_DISPLAY, Store

_CHAIN_ORDER = {"paknsave": 0, "newworld": 1}


def normalise_name(text: str) -> str:
    """Case-fold, collapse whitespace, and drop apostrophes.

    Foodstuffs spells one Auckland store ``PAKnSAVE`` and the rest
    ``PAK'nSAVE``. Both forms compare equal after this.
    """
    cleaned = str(text).replace("’", "'").replace("`", "'").replace("'", "")
    return " ".join(cleaned.split()).casefold()


def match_store(stores: list[Store], query: str) -> Store:
    """Pick one store.

    Exact id (case-insensitive) wins. Otherwise match a case-insensitive name
    substring. If several names match, prefer the one whose normalised name
    equals the query, or equals ``"<chain display name> <query>"``, unless that
    chain-prefixed name is only a prefix of another candidate (so ``Ashburton``
    stays ambiguous between New World Example and New World Example South,
    while the full name ``New World Example`` selects the exact store).
    """
    needle = query.strip()
    if not needle:
        raise StoreNotFound(query)

    folded = needle.casefold()
    id_hits = [store for store in stores if store.id.casefold() == folded]
    if len(id_hits) == 1:
        return id_hits[0]
    if len(id_hits) > 1:
        raise AmbiguousStore(query, id_hits)

    normalised_query = normalise_name(needle)
    substring = [store for store in stores if normalised_query in normalise_name(store.name)]
    if not substring:
        raise StoreNotFound(query)
    if len(substring) == 1:
        return substring[0]

    preferred = [store for store in substring if _is_preferred(store, needle, substring)]
    if len(preferred) == 1:
        return preferred[0]
    if len(preferred) > 1:
        raise AmbiguousStore(query, preferred)
    raise AmbiguousStore(query, substring)


def _is_preferred(store: Store, query: str, candidates: list[Store]) -> bool:
    name = normalise_name(store.name)
    normalised_query = normalise_name(query)
    if name == normalised_query:
        return True
    display = CHAIN_DISPLAY.get(store.chain, store.chain)
    prefixed = normalise_name(f"{display} {query}")
    if name != prefixed:
        return False
    for other in candidates:
        if other.chain == store.chain and other.id == store.id:
            continue
        if normalise_name(other.name).startswith(name + " "):
            return False
    return True


def store_to_dict(store: Store) -> dict:
    return store.to_dict()


def store_in_region(store: Store, region: str) -> bool:
    """Case-insensitive region match. ``all`` keeps every store.

    ``auckland`` also matches a catalogue area of Waiheke Island or any area
    whose name starts with Auckland, including stores whose normalised region
    is already ``Auckland``.
    """
    wanted = region.strip().casefold()
    if wanted in {"", "all"}:
        return True
    label = (store.region or "").casefold()
    if label == wanted:
        return True
    area = str((store.extra or {}).get("area") or "").casefold()
    if area == wanted:
        return True
    if wanted == "auckland" and (area.startswith("auckland") or area == "waiheke island"):
        return True
    return False


def store_matches_text(store: Store, query: str) -> bool:
    """Case-insensitive match against the name, suburb, city, area, or address."""
    needle = normalise_name(query)
    if not needle:
        return True
    extra = store.extra or {}
    blob = " ".join(
        part
        for part in (
            store.name,
            store.suburb,
            store.address,
            str(extra.get("city") or ""),
            str(extra.get("area") or ""),
        )
        if part
    )
    return needle in normalise_name(blob)


def filter_stores(
    stores: list[Store],
    *,
    chain: str | None = None,
    region: str | None = None,
    city: str | None = None,
    search: str | None = None,
) -> list[Store]:
    selected = list(stores)
    if chain:
        selected = [store for store in selected if store.chain == chain]
    if region:
        selected = [store for store in selected if store_in_region(store, region)]
    if city and city.strip():
        selected = [store for store in selected if _place_match(store, city)]
    if search and search.strip():
        needle = normalise_name(search)
        selected = [
            store
            for store in selected
            if needle in normalise_name(store.name) or _place_match(store, search)
        ]
    return selected


def _place_match(store: Store, query: str) -> bool:
    needle = normalise_name(query)
    extra = store.extra or {}
    blob = " ".join(
        part
        for part in (
            store.suburb,
            store.address,
            str(extra.get("city") or ""),
            str(extra.get("area") or ""),
        )
        if part
    )
    return needle in normalise_name(blob)


def region_counts(stores: list[Store]) -> list[dict]:
    """Region names with store counts, largest first."""
    counts: dict[str, int] = {}
    for store in stores:
        name = store.region or ""
        counts[name] = counts.get(name, 0) + 1
    rows = [{"region": name, "stores": count} for name, count in counts.items()]
    rows.sort(key=lambda row: (-row["stores"], row["region"].casefold()))
    return rows


def store_from_dict(data: dict) -> Store:
    return Store(
        chain=data["chain"],
        id=str(data["id"]),
        name=data.get("name") or "",
        address=data.get("address") or "",
        suburb=data.get("suburb"),
        region=data.get("region"),
        postcode=str(data["postcode"]) if data.get("postcode") else None,
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        extra=data.get("extra"),
    )


BUNDLED_FILENAME = "nz.json"


def bundled_store_path() -> Path:
    import nzgrocery

    return Path(nzgrocery.__file__).resolve().parent / "stores" / BUNDLED_FILENAME


def load_bundled_stores() -> list[Store]:
    """Load ``stores/nz.json`` via importlib.resources."""
    resource = files("nzgrocery").joinpath("stores").joinpath(BUNDLED_FILENAME)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    raw_stores = payload["stores"] if isinstance(payload, dict) else payload
    return [store_from_dict(item) for item in raw_stores]


def load_store_file(path: Path) -> list[Store]:
    """Read a store-list JSON file. A missing file is an empty list."""
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_stores = payload["stores"] if isinstance(payload, dict) else payload
    return [store_from_dict(item) for item in raw_stores]


def cached_live_stores(chain: str) -> list[Store] | None:
    """Stores from a fresh reference-cache file, or ``None`` when that file cannot be reused."""
    from nzgrocery.reference import load_store_payload

    payload = load_store_payload(chain)
    if payload is None:
        return None
    from nzgrocery.foodstuffs import stores_from_payload

    return stores_from_payload(payload, chain)


def find_store_locally(chain: str, query: str) -> Store:
    """Resolve ``query`` from the bundled list, then a fresh cached live list.

    Raises :class:`StoreNotFound` when neither source has a match, and
    :class:`AmbiguousStore` when a source has several. An expired live cache
    is ignored so the caller can fetch it again.
    """
    bundled = [store for store in load_bundled_stores() if store.chain == chain]
    try:
        return match_store(bundled, query)
    except StoreNotFound:
        pass
    cached = cached_live_stores(chain)
    if not cached:
        raise StoreNotFound(query)
    return match_store(cached, query)


def build_store_list(pns_payload: dict, nw_payload: dict) -> list[Store]:
    """Every store in the two live catalogue payloads."""
    from nzgrocery.foodstuffs import stores_from_payload

    stores: list[Store] = []
    stores.extend(stores_from_payload(pns_payload, "paknsave"))
    stores.extend(stores_from_payload(nw_payload, "newworld"))
    stores.sort(key=lambda store: (_CHAIN_ORDER.get(store.chain, 9), store.name.casefold(), store.id))
    return stores


def build_auckland_list(pns_payload: dict, nw_payload: dict) -> list[Store]:
    """Auckland stores from the nationwide list."""
    return [
        store
        for store in build_store_list(pns_payload, nw_payload)
        if store_in_region(store, "auckland")
    ]


def write_store_list(path: Path, stores: list[Store], *, generated_at: str | None = None) -> None:
    from nzgrocery.cache import now_nz

    counts = {chain: 0 for chain in ("paknsave", "newworld")}
    for store in stores:
        counts[store.chain] = counts.get(store.chain, 0) + 1
    payload = {
        "generated_at": generated_at or now_nz().isoformat(timespec="seconds"),
        "coverage": "NZ",
        "counts": counts,
        "stores": [store_to_dict(store) for store in stores],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
