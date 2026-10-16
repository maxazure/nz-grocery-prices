"""Errors the CLI maps onto process exit codes."""

from __future__ import annotations


class GroceryError(Exception):
    """Base class for expected client failures."""


class StoreNotFound(GroceryError):
    def __init__(self, query: str, *, hint: str | None = None) -> None:
        self.query = query
        message = f"no store matched {query!r}"
        if hint:
            message = f"{message}. {hint}"
        super().__init__(message)


class AmbiguousStore(GroceryError):
    def __init__(self, query: str, candidates: list) -> None:
        self.query = query
        self.candidates = list(candidates)
        rendered = []
        for store in self.candidates:
            name = getattr(store, "name", None)
            ident = getattr(store, "id", None)
            chain = getattr(store, "chain", None)
            if name is None and isinstance(store, dict):
                name = store.get("name")
                ident = store.get("id")
                chain = store.get("chain")
            region = getattr(store, "region", None)
            if region is None and isinstance(store, dict):
                region = store.get("region")
            rendered.append(f"{name} (chain={chain}, id={ident}, region={region})")
        listing = "; ".join(rendered)
        super().__init__(
            f"store query {query!r} matched {len(self.candidates)} stores: {listing}. "
            "Pass a store id or a more specific name."
        )


class StoreVerificationError(GroceryError):
    """The live site did not confirm the store we intended to read."""


class Blocked(GroceryError):
    """HTTP or anti-bot failure. Nothing was saved."""


class NoRows(GroceryError):
    """The catalogue returned nothing we could keep. Nothing was saved."""
