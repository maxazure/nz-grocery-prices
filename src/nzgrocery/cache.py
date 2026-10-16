"""Local price cache derived from the insert-only ``prices`` table.

A snapshot is the set of rows that share ``(chain, store_id, store,
department, fetched_at)``. The New Zealand calendar date is ``fetched_at``
parsed with ``datetime.fromisoformat`` and converted to Pacific/Auckland.
Naive timestamps are already New Zealand local time.

Clients write the selected Foodstuffs store UUID on every row.
Offline resolution uses those same ids.
"""

from __future__ import annotations

import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nzgrocery.errors import AmbiguousStore, StoreNotFound
from nzgrocery.models import PRICE_COLUMNS
from nzgrocery.stores import load_bundled_stores, match_store, normalise_name

NZ = ZoneInfo("Pacific/Auckland")
DB_FILENAME = "prices.sqlite"


def now_nz() -> datetime:
    """Current time in Pacific/Auckland. Tests monkeypatch this."""
    return datetime.now(NZ)


def _as_nz(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=NZ)
    return moment.astimezone(NZ)


def nz_today(now: datetime | None = None) -> date:
    moment = now if now is not None else now_nz()
    return _as_nz(moment).date()


def nz_date_of(fetched_at: str) -> date:
    return _as_nz(datetime.fromisoformat(fetched_at)).date()


def latest_fetched_at(values: list[str | None]) -> str | None:
    best_at: datetime | None = None
    best_raw: str | None = None
    for raw in values:
        if not raw:
            continue
        try:
            parsed = _as_nz(datetime.fromisoformat(raw))
        except ValueError:
            continue
        if best_at is None or parsed > best_at:
            best_at = parsed
            best_raw = raw
    return best_raw


def default_db_path() -> Path:
    """Cache file. ``NZGROCERY_DB`` wins, then ``NZGROCERY_DATA``, then the platform dir."""
    explicit = os.environ.get("NZGROCERY_DB")
    if explicit:
        return Path(explicit).expanduser()
    data = os.environ.get("NZGROCERY_DATA")
    if data:
        return Path(data).expanduser() / DB_FILENAME
    return platform_data_dir() / DB_FILENAME


def platform_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "nz-grocery-prices"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local).expanduser() if local else Path.home() / "AppData" / "Local"
        return base / "nz-grocery-prices"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "nz-grocery-prices"


def min_interval_minutes() -> int:
    raw = os.environ.get("NZGROCERY_MIN_INTERVAL_MINUTES", "10")
    try:
        value = int(str(raw).strip())
    except ValueError:
        return 10
    return max(0, value)


@dataclass(frozen=True)
class Snapshot:
    chain: str
    store_id: str
    store: str
    department: str
    fetched_at: str
    rows: int

    @property
    def nz_date(self) -> date:
        return nz_date_of(self.fetched_at)

    def to_dict(self, *, today: date | None = None) -> dict:
        payload = {
            "date": self.nz_date.isoformat(),
            "chain": self.chain,
            "store": self.store,
            "store_id": self.store_id,
            "department": self.department,
            "fetched_at": self.fetched_at,
            "rows": self.rows,
        }
        if today is not None:
            payload["today"] = self.nz_date == today
        return payload


def _connect_readonly(db: str | Path) -> sqlite3.Connection | None:
    """Open an existing database. A missing file is not created."""
    path = Path(db)
    if not path.is_file():
        return None
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def list_snapshots(
    db: str | Path,
    chain: str | None = None,
    store_id: str | None = None,
    department: str | None = None,
    date: date | None = None,
    since: date | None = None,
) -> list[Snapshot]:
    """Snapshots newest first. ``date`` and ``since`` are Pacific/Auckland calendar dates."""
    connection = _connect_readonly(db)
    if connection is None:
        return []
    clauses: list[str] = []
    params: list[str] = []
    if chain:
        clauses.append("chain = ?")
        params.append(chain)
    if store_id:
        clauses.append("store_id = ?")
        params.append(store_id)
    if department:
        clauses.append("department = ?")
        params.append(department)
    sql = (
        "SELECT chain, store_id, store, department, fetched_at, COUNT(*) AS n "
        "FROM prices"
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " GROUP BY chain, store_id, store, department, fetched_at"
    try:
        try:
            fetched = connection.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        connection.close()

    snapshots: list[Snapshot] = []
    for row in fetched:
        fetchd = row["fetched_at"]
        try:
            nz_date = nz_date_of(fetchd)
        except ValueError:
            continue
        if date is not None and nz_date != date:
            continue
        if since is not None and nz_date < since:
            continue
        snapshots.append(
            Snapshot(
                chain=row["chain"],
                store_id=str(row["store_id"]),
                store=row["store"] or "",
                department=row["department"] or "",
                fetched_at=fetchd,
                rows=int(row["n"]),
            )
        )
    snapshots.sort(key=_snapshot_sort_key, reverse=True)
    return snapshots


def _snapshot_sort_key(snapshot: Snapshot) -> datetime:
    try:
        return _as_nz(datetime.fromisoformat(snapshot.fetched_at))
    except ValueError:
        return datetime.min.replace(tzinfo=NZ)


def latest_snapshot(
    db: str | Path,
    chain: str,
    store_id: str,
    department: str,
    date: date | None = None,
) -> Snapshot | None:
    """Newest snapshot for one store and department. ``date`` limits it to that NZ day."""
    found = list_snapshots(db, chain=chain, store_id=store_id, department=department, date=date)
    return found[0] if found else None


def snapshot_rows(db: str | Path, snapshot: Snapshot) -> list[dict]:
    connection = _connect_readonly(db)
    if connection is None:
        return []
    columns = ", ".join(PRICE_COLUMNS)
    try:
        try:
            fetched = connection.execute(
                f"SELECT {columns} FROM prices "
                "WHERE chain = ? AND store_id = ? AND IFNULL(department, '') = ? AND fetched_at = ? "
                "ORDER BY id",
                (snapshot.chain, snapshot.store_id, snapshot.department, snapshot.fetched_at),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        connection.close()
    return [{key: row[key] for key in row.keys()} for row in fetched]


def select_snapshots(
    db: str | Path,
    *,
    chain: str | None = None,
    store_id: str | None = None,
    stores: list[tuple[str, str]] | None = None,
    department: str | None = None,
    on_date: date | None = None,
    latest: bool = False,
) -> list[Snapshot]:
    """Latest snapshot per chain, store, and department.

    ``latest`` keeps the newest snapshot of any date. Otherwise ``on_date``
    restricts the choice to that Pacific/Auckland day (pass ``None`` with
    ``latest=False`` to apply no date filter before picking the newest).
    """
    if department in (None, "", "all"):
        allowed = {"produce", "meat"}
        department_filter = None
    else:
        allowed = {department}
        department_filter = department
    single_store = None if stores else store_id
    single_chain = None if stores else chain
    found = list_snapshots(
        db,
        chain=single_chain,
        store_id=single_store,
        department=department_filter,
        date=None if latest else on_date,
    )
    if stores:
        wanted = {(item_chain, item_store) for item_chain, item_store in stores}
        found = [snap for snap in found if (snap.chain, snap.store_id) in wanted]
    chosen: dict[tuple[str, str, str], Snapshot] = {}
    for snap in found:
        if snap.department not in allowed:
            continue
        key = (snap.chain, snap.store_id, snap.department)
        chosen.setdefault(key, snap)
    return sorted(chosen.values(), key=lambda snap: (snap.chain, snap.store.casefold(), snap.department))


def query_prices(
    db: str | Path,
    *,
    chain: str | None = None,
    store_id: str | None = None,
    stores: list[tuple[str, str]] | None = None,
    department: str | None = None,
    search: list[str] | None = None,
    on_date: date | None = None,
    latest: bool = False,
    sort: str = "price",
    limit: int = 0,
) -> tuple[list[dict], list[Snapshot]]:
    """Return ``(rows, snapshots)``.

    ``snapshots`` is the local data in scope before the product-name search,
    so callers can tell a missing snapshot from a search that matched nothing.
    """
    snapshots = select_snapshots(
        db,
        chain=chain,
        store_id=store_id,
        stores=stores,
        department=department,
        on_date=on_date,
        latest=latest,
    )
    rows: list[dict] = []
    for snap in snapshots:
        rows.extend(snapshot_rows(db, snap))
    needles = [term.casefold() for term in (search or []) if term and term.strip()]
    if needles:
        rows = [
            row
            for row in rows
            if any(needle in (row.get("name") or "").casefold() for needle in needles)
        ]
    if sort == "name":
        rows.sort(key=lambda row: ((row.get("name") or "").casefold(), float(row.get("price_nzd") or 0)))
    else:
        rows.sort(key=lambda row: (float(row.get("price_nzd") or 0), (row.get("name") or "").casefold()))
    if limit and limit > 0:
        rows = rows[:limit]
    return rows, snapshots


def minutes_until_refresh(snapshot: Snapshot | None, now: datetime | None = None) -> int | None:
    """Minutes until ``--no-cache`` may hit the network, or ``None`` if it may.

    ``NZGROCERY_MIN_INTERVAL_MINUTES`` defaults to 10. ``0`` disables the guard.
    """
    if snapshot is None:
        return None
    interval = min_interval_minutes()
    if interval <= 0:
        return None
    moment = _as_nz(now if now is not None else now_nz())
    try:
        fetchd = _as_nz(datetime.fromisoformat(snapshot.fetched_at))
    except ValueError:
        return None
    remaining = timedelta(minutes=interval) - (moment - fetchd)
    if remaining.total_seconds() <= 0:
        return None
    return max(1, math.ceil(remaining.total_seconds() / 60))


def resolve_store_offline(chain: str, query: str, db: str | Path) -> tuple[str, str] | None:
    """Return ``(store_id, store_name)`` without the network.

    The bundled nationwide list is matched with the same rules as ``nzgrocery
    stores``. If that list has no match, distinct ``(store_id, store)`` pairs
    already cached for ``chain`` are tried (exact id, or a case-insensitive
    name substring). Ambiguous matches are unresolved (``None``).
    """
    bundled = [store for store in load_bundled_stores() if store.chain == chain]
    try:
        match = match_store(bundled, query)
    except StoreNotFound:
        match = None
    except AmbiguousStore:
        return None
    if match is not None:
        return match.id, match.name
    return _match_cached_store(chain, query, db)


def _match_cached_store(chain: str, query: str, db: str | Path) -> tuple[str, str] | None:
    connection = _connect_readonly(db)
    if connection is None:
        return None
    try:
        try:
            pairs = connection.execute(
                "SELECT DISTINCT store_id, store FROM prices WHERE chain = ?",
                (chain,),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
    finally:
        connection.close()
    needle = query.strip()
    if not needle:
        return None
    folded = needle.casefold()
    id_hits: dict[str, str] = {}
    for row in pairs:
        store_id = str(row["store_id"])
        if store_id.casefold() == folded:
            id_hits.setdefault(store_id, row["store"] or "")
    if len(id_hits) == 1:
        return next(iter(id_hits.items()))
    if len(id_hits) > 1:
        return None
    normalised = normalise_name(needle)
    name_hits: dict[str, str] = {}
    for row in pairs:
        store_name = row["store"] or ""
        if normalised and normalised in normalise_name(store_name):
            name_hits.setdefault(str(row["store_id"]), store_name)
    if len(name_hits) == 1:
        return next(iter(name_hits.items()))
    return None
