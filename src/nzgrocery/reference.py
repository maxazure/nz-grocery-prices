"""Local copies of store lists and category trees.

These files live in ``<data dir>/reference/``, next to the price database from
:func:`nzgrocery.cache.default_db_path`. Session tokens and cookies are not
written here. A file is reused until it is older than its TTL. Set
``NZGROCERY_REFERENCE_TTL_DAYS`` to an integer to override every TTL at once
(``0`` means always refresh).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from nzgrocery.cache import _as_nz, default_db_path, now_nz

STORE_LIST_TTL_DAYS = 7
CATEGORY_TTL_DAYS = 7

_KIND_TTL = {
    "stores": STORE_LIST_TTL_DAYS,
    "categories": CATEGORY_TTL_DAYS,
}


def ttl_days(kind: str) -> int:
    """TTL in days for ``stores``, ``categories``,."""
    override = os.environ.get("NZGROCERY_REFERENCE_TTL_DAYS")
    if override is not None and str(override).strip() != "":
        try:
            return max(0, int(str(override).strip()))
        except ValueError:
            pass
    try:
        return _KIND_TTL[kind]
    except KeyError as exc:
        raise ValueError(f"unknown reference kind {kind!r}") from exc


def reference_dir() -> Path:
    """Directory of cached reference files. It is the parent of the default database."""
    return default_db_path().parent / "reference"


def store_list_path(chain: str) -> Path:
    return reference_dir() / f"stores-{chain}.json"


def categories_path(chain: str) -> Path:
    return reference_dir() / f"{chain}-categories.json"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _age_seconds(fetched_at: str | None, now: datetime | None = None) -> int | None:
    if not fetched_at:
        return None
    try:
        parsed = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None
    moment = _as_nz(now if now is not None else now_nz())
    return int((moment - _as_nz(parsed)).total_seconds())


def is_fresh(fetched_at: str | None, kind: str, now: datetime | None = None) -> bool:
    age = _age_seconds(fetched_at, now)
    if age is None:
        return False
    if age < 0:
        return True
    return age <= ttl_days(kind) * 86400


def save_store_payload(chain: str, payload: dict, *, fetched_at: str | None = None) -> Path:
    path = store_list_path(chain)
    _write(
        path,
        {
            "fetched_at": fetched_at or now_nz().isoformat(timespec="seconds"),
            "chain": chain,
            "payload": payload,
        },
    )
    return path


def load_store_payload(chain: str, *, force: bool = False, now: datetime | None = None) -> dict | None:
    """Raw store-list payload, or ``None`` when missing, expired, or ``force``."""
    if force:
        return None
    data = _read(store_list_path(chain))
    if not data or "payload" not in data:
        return None
    if not is_fresh(data.get("fetched_at"), "stores", now):
        return None
    payload = data["payload"]
    return payload if isinstance(payload, dict) else None


def load_or_fetch_store_payload(chain: str, fetch, *, force: bool = False) -> dict:
    """Return a fresh cached payload, or call ``fetch``, save it, and return that."""
    cached = load_store_payload(chain, force=force)
    if cached is not None:
        return cached
    payload = fetch()
    if not isinstance(payload, dict):
        raise TypeError(f"{chain} store list was not a JSON object")
    save_store_payload(chain, payload)
    return payload


def save_categories(chain: str, categories: dict, *, fetched_at: str | None = None) -> Path:
    path = categories_path(chain)
    _write(
        path,
        {
            "fetched_at": fetched_at or now_nz().isoformat(timespec="seconds"),
            "chain": chain,
            "categories": categories,
        },
    )
    return path


def load_categories(chain: str, *, force: bool = False, now: datetime | None = None) -> dict | None:
    if force:
        return None
    data = _read(categories_path(chain))
    if not data or not isinstance(data.get("categories"), dict):
        return None
    if not is_fresh(data.get("fetched_at"), "categories", now):
        return None
    return data["categories"]


def load_or_fetch_categories(chain: str, fetch, *, force: bool = False) -> dict:
    cached = load_categories(chain, force=force)
    if cached is not None:
        return cached
    categories = fetch()
    if not isinstance(categories, dict):
        raise TypeError(f"{chain} categories were not a JSON object")
    save_categories(chain, categories)
    return categories


def reference_status(now: datetime | None = None) -> list[dict]:
    """One record per reference file that exists: file, fetched_at, age, ttl, expired."""
    moment = now if now is not None else now_nz()
    specs: list[tuple[Path, str, str | None]] = []
    for chain in ("paknsave", "newworld"):
        specs.append((store_list_path(chain), "stores", chain))
        specs.append((categories_path(chain), "categories", chain))
    rows = []
    for path, kind, chain in specs:
        data = _read(path)
        if data is None:
            continue
        fetched_at = data.get("fetched_at")
        age = _age_seconds(fetched_at if isinstance(fetched_at, str) else None, moment)
        ttl = ttl_days(kind)
        expired = True if age is None else age < 0 or age > ttl * 86400
        if age is not None and age < 0:
            expired = False
        row = {
            "file": str(path),
            "kind": kind,
            "fetched_at": fetched_at,
            "age": age,
            "ttl": ttl,
            "expired": expired,
        }
        if chain:
            row["chain"] = chain
        rows.append(row)
    return rows
