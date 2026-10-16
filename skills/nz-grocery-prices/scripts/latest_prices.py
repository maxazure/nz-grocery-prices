#!/usr/bin/env python3
"""Print the latest price snapshot from an nzgrocery SQLite file.

Standard library only (no nzgrocery install required). Prefer `nz-grocery-prices prices`
when the package is installed; it uses the same default database.

The default path matches nzgrocery: NZGROCERY_DB, else NZGROCERY_DATA/prices.sqlite,
else the platform data directory.

Examples:

    python3 latest_prices.py
    python3 latest_prices.py --chain newworld --store "Browns Bay" --search banana
    python3 latest_prices.py /path/to/prices.sqlite --json --limit 0
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

COLUMNS = ("chain", "store", "department", "name", "price_nzd", "unit_or_size", "price_per", "raw_price_text")


def default_db_path() -> Path:
    """Same rules as nzgrocery.cache.default_db_path, with no package import."""
    explicit = os.environ.get("NZGROCERY_DB")
    if explicit:
        return Path(explicit).expanduser()
    data = os.environ.get("NZGROCERY_DATA")
    if data:
        return Path(data).expanduser() / "prices.sqlite"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "nz-grocery-prices"
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        root = Path(local).expanduser() if local else Path.home() / "AppData" / "Local"
        base = root / "nz-grocery-prices"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        root = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
        base = root / "nz-grocery-prices"
    return base / "prices.sqlite"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Latest nzgrocery snapshot per chain/store")
    parser.add_argument(
        "db",
        nargs="?",
        default=None,
        help="SQLite file (default: NZGROCERY_DB / platform data dir / prices.sqlite)",
    )
    parser.add_argument("--chain", choices=("paknsave", "newworld"))
    parser.add_argument("--store", help="Store name fragment or exact store_id")
    parser.add_argument("--department", choices=("produce", "meat"))
    parser.add_argument("--search", help="Product name fragment (case-insensitive)")
    parser.add_argument("--limit", type=int, default=50, help="Max rows, 0 = no limit (default 50)")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args(argv)
    db_path = args.db or str(default_db_path())

    where, params = [], []
    if args.chain:
        where.append("chain = ?")
        params.append(args.chain)
    if args.store:
        where.append("(store_id = ? OR store LIKE ?)")
        params.extend([args.store, f"%{args.store}%"])
    scope = " AND ".join(where) or "1=1"

    sql = f"""
        WITH latest AS (
            SELECT chain, store_id, MAX(fetched_at) AS ts FROM prices
            WHERE {scope} GROUP BY chain, store_id
        )
        SELECT p.fetched_at, {", ".join("p." + c for c in COLUMNS)}
        FROM prices p JOIN latest l
          ON p.chain = l.chain AND p.store_id = l.store_id AND p.fetched_at = l.ts
        WHERE 1=1
    """
    if args.department:
        sql += " AND p.department = ?"
        params.append(args.department)
    if args.search:
        sql += " AND p.name LIKE ?"
        params.append(f"%{args.search}%")
    sql += " ORDER BY p.chain, p.store, p.price_nzd"
    if args.limit > 0:
        sql += f" LIMIT {int(args.limit)}"

    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        print(f"cannot open {db_path}: {exc}", file=sys.stderr)
        return 1
    connection.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in connection.execute(sql, params)]
    except sqlite3.OperationalError as exc:
        print(f"query failed ({exc}); is this an nzgrocery SQLite file?", file=sys.stderr)
        return 1
    finally:
        connection.close()

    if args.json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    if not rows:
        print("no rows", file=sys.stderr)
        return 0
    print(f"snapshot(s): {', '.join(sorted({r['fetched_at'] for r in rows}))}")
    for row in rows:
        extra = f"  [{row['raw_price_text']}]" if row["raw_price_text"] and row["raw_price_text"] != f"${row['price_nzd']:.2f}" else ""
        print(f"{row['store']:<28.28} {row['name']:<50.50} ${row['price_nzd']:>7.2f}  {row['unit_or_size'] or '':<10} {row['price_per'] or ''}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
