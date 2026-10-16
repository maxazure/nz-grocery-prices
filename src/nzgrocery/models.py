"""Store and price-row records."""

from __future__ import annotations

from dataclasses import dataclass, field

# Public chain keys used by the CLI and the bundled store list.
CHAINS = ("paknsave", "newworld")

CHAIN_DISPLAY = {
    "paknsave": "PAK'nSAVE",
    "newworld": "New World",
}

PRICE_COLUMNS = (
    "fetched_at",
    "chain",
    "store_id",
    "store",
    "department",
    "category",
    "name",
    "price_nzd",
    "unit_or_size",
    "price_per",
    "product_url",
    "raw_price_text",
    "product_id",
)


@dataclass
class Store:
    """One supermarket the public catalogue can price against.

    ``suburb`` is the suburb when the chain provides one, otherwise the city.
    ``extra`` holds public catalogue fields such as online availability. It never holds phone numbers or account data.
    """

    chain: str
    id: str
    name: str
    address: str
    suburb: str | None = None
    region: str | None = None
    postcode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    extra: dict | None = field(default=None)

    def to_dict(self) -> dict:
        data = {
            "chain": self.chain,
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "suburb": self.suburb,
            "region": self.region,
            "postcode": self.postcode,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
        if self.extra:
            data["extra"] = dict(self.extra)
        return data


@dataclass
class PriceRow:
    """One insert-only price snapshot."""

    fetched_at: str
    chain: str
    store_id: str
    store: str
    department: str
    category: str | None
    name: str
    price_nzd: float
    unit_or_size: str | None = None
    price_per: str | None = None
    product_url: str | None = None
    raw_price_text: str | None = None
    product_id: str | None = None

    def as_dict(self) -> dict:
        return {column: getattr(self, column) for column in PRICE_COLUMNS}
