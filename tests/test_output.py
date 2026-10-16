"""Writers for sqlite, csv, json, and jsonl."""

import json
import sqlite3

from nzgrocery.cache import default_db_path
from nzgrocery.output import dated_output_path, default_output_path, write_rows

ROW = {
    "fetched_at": "2026-10-12T09:00:00+13:00",
    "chain": "newworld",
    "store_id": "773ad0a0-024e-46c5-a94b-df1cf86d25cc",
    "store": "New World Albany",
    "department": "produce",
    "category": "Fruit & Veg / Fruit",
    "name": "Bananas",
    "price_nzd": 3.49,
    "unit_or_size": "kg",
    "price_per": "$3.49 / 1kg",
    "product_url": "https://www.newworld.co.nz/shop/product-details/1/bananas",
    "raw_price_text": "$3.49",
    "product_id": "1",
}


def test_default_names():
    stamp = "20261012T090000"
    assert default_output_path("sqlite", "paknsave", "PAK'nSAVE Albany", "all", stamp) == str(default_db_path())
    assert default_output_path("csv", "paknsave", "PAK'nSAVE Albany", "all", stamp) == (
        "prices-paknsave-paknsave-albany-all-20261012T090000.csv"
    )
    assert default_output_path("jsonl", "newworld", "New World Albany", "produce", stamp).endswith(
        ".jsonl"
    )
    dated = dated_output_path(
        "csv", "newworld", "New World Albany", "produce", "2026-10-12", default_db_path().parent
    )
    assert dated.name == "newworld-new-world-albany-produce-2026-10-12.csv"


def test_sqlite_is_insert_only_and_indexed(tmp_path):
    path = tmp_path / "prices.sqlite"
    write_rows([ROW], "sqlite", path)
    second = dict(ROW, fetched_at="2026-10-13T09:00:00+13:00", price_nzd=3.99)
    write_rows([second], "sqlite", path)
    connection = sqlite3.connect(path)
    try:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(prices)")]
        assert columns[0] == "id"
        assert "chain" in columns and "store_id" in columns and "department" in columns
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'prices'"
            )
        }
        assert "idx_prices_chain_store_fetched" in indexes
        assert "idx_prices_chain_store_dept_fetched" in indexes
        assert "idx_prices_product_id" in indexes
        saved = connection.execute(
            "SELECT price_nzd, fetched_at FROM prices ORDER BY id"
        ).fetchall()
        assert len(saved) == 2
        assert saved[0][0] == 3.49
        assert saved[1][1].startswith("2026-10-13")
    finally:
        connection.close()


def test_csv_json_and_jsonl(tmp_path):
    csv_path = tmp_path / "prices.csv"
    write_rows([ROW], "csv", str(csv_path))
    text = csv_path.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("fetched_at,chain,store_id,store,department")
    assert "Bananas" in text
    assert "3.49" in text

    json_path = tmp_path / "prices.json"
    write_rows([ROW], "json", str(json_path))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[0]["product_id"] == "1"
    assert payload[0]["price_nzd"] == 3.49

    jsonl_path = tmp_path / "nested" / "prices.jsonl"
    write_rows([ROW, dict(ROW, product_id="2", name="Apples")], "jsonl", str(jsonl_path))
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["name"] == "Apples"


def test_stdout_csv(capsys):
    assert write_rows([ROW], "csv", "-") == "-"
    captured = capsys.readouterr()
    assert "Bananas" in captured.out
    assert captured.err == ""
