"""Write price snapshots to SQLite, CSV, JSON, or JSONL.

SQLite is insert-only: each fetch appends a new snapshot and leaves older
rows in place.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from datetime import date
from io import StringIO
from pathlib import Path

from nzgrocery.models import PRICE_COLUMNS

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at TEXT NOT NULL,
    chain TEXT NOT NULL,
    store_id TEXT NOT NULL,
    store TEXT NOT NULL,
    department TEXT,
    category TEXT,
    name TEXT NOT NULL,
    price_nzd REAL NOT NULL,
    unit_or_size TEXT,
    price_per TEXT,
    product_url TEXT,
    raw_price_text TEXT,
    product_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_prices_chain_store_fetched
    ON prices (chain, store_id, fetched_at);
CREATE INDEX IF NOT EXISTS idx_prices_chain_store_dept_fetched
    ON prices (chain, store_id, department, fetched_at);
CREATE INDEX IF NOT EXISTS idx_prices_product_id
    ON prices (product_id);
"""

INSERT_SQL = f"""
INSERT INTO prices ({", ".join(PRICE_COLUMNS)})
VALUES ({", ".join(":" + column for column in PRICE_COLUMNS)})
"""


def normalise_row(row: dict) -> dict:
    cleaned = {}
    for column in PRICE_COLUMNS:
        value = row.get(column)
        if column == "price_nzd" and value is not None:
            value = float(value)
        cleaned[column] = value
    return cleaned


def slugify(text: str) -> str:
    cleaned = str(text).replace("'", "").replace("’", "")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", cleaned).strip("-").lower()
    return slug or "store"


def dated_output_path(
    fmt: str,
    chain: str,
    store_name: str,
    department: str,
    nz_date: date | str,
    data_dir: str | Path,
) -> Path:
    """Deterministic export path beside the cache database.

    ``<data dir>/<chain>-<store-slug>-<department>-<YYYY-MM-DD>.<ext>``.
    SQLite returns ``<data dir>/prices.sqlite``; the CLI uses ``default_db_path``
    for the real database so ``NZGROCERY_DB`` still wins.
    """
    directory = Path(data_dir)
    if fmt == "sqlite":
        return directory / "prices.sqlite"
    extension = {"csv": "csv", "json": "json", "jsonl": "jsonl"}[fmt]
    day = nz_date.isoformat() if isinstance(nz_date, date) else str(nz_date)
    filename = f"{chain}-{slugify(store_name)}-{department}-{day}.{extension}"
    return directory / filename


def default_output_path(fmt: str, chain: str, store_name: str, department: str, stamp: str) -> str:
    """Compatibility helper.

    SQLite delegates to the platform cache path. CSV/JSON/JSONL keep the
    historical timestamped name; new fetches use :func:`dated_output_path`.
    """
    if fmt == "sqlite":
        from nzgrocery.cache import default_db_path

        return str(default_db_path())
    extension = {"csv": "csv", "json": "json", "jsonl": "jsonl"}[fmt]
    return f"prices-{chain}-{slugify(store_name)}-{department}-{stamp}.{extension}"


def read_rows(path: str | Path, fmt: str) -> list[dict]:
    """Load a CSV, JSON, or JSONL snapshot written by :func:`write_rows`."""
    text = Path(path).read_text(encoding="utf-8")
    if fmt == "json":
        if not text.strip():
            return []
        payload = json.loads(text)
        if not isinstance(payload, list):
            return []
        return [row for row in payload if isinstance(row, dict)]
    if fmt == "jsonl":
        rows = []
        for line in text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        return rows
    if fmt == "csv":
        return [dict(row) for row in csv.DictReader(StringIO(text))]
    raise ValueError(f"unknown format {fmt!r}")


def write_rows(rows: list[dict], fmt: str, dest: str | Path) -> str:
    """Write ``rows``. ``dest`` may be ``-`` for stdout (not sqlite).

    Returns the destination description stored in the JSON summary.
    """
    cleaned = [normalise_row(row) for row in rows]
    if fmt == "sqlite":
        if str(dest) == "-":
            raise ValueError("sqlite output cannot be stdout; pass a file path")
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_sqlite(path, cleaned)
        return str(path)
    text = render_text(cleaned, fmt)
    if str(dest) == "-":
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return "-"
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def render_text(rows: list[dict], fmt: str) -> str:
    if fmt == "csv":
        return _render_csv(rows)
    if fmt == "json":
        return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    if fmt == "jsonl":
        return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    raise ValueError(f"unknown format {fmt!r}")


def _render_csv(rows: list[dict]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(PRICE_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in PRICE_COLUMNS})
    return buffer.getvalue()


def _write_sqlite(path: Path, rows: list[dict]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(CREATE_SQL)
        connection.executemany(INSERT_SQL, rows)
        connection.commit()
    finally:
        connection.close()
