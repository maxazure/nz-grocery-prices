"""CLI parsing and the offline stores command."""

import json

import pytest

from nzgrocery.cli import build_parser, bundled_suggestion, count_rows, main
from nzgrocery.foodstuffs import DEPARTMENTS as FS_DEPARTMENTS


def test_fetch_parser_defaults():
    args = build_parser().parse_args(
        ["fetch", "--chain", "newworld", "--store", "Browns Bay", "--dry-run", "-v"]
    )
    assert args.chain == "newworld"
    assert args.store == "Browns Bay"
    assert args.department == "produce"
    assert args.format == "sqlite"
    assert args.output is None
    assert args.dry_run is True
    assert args.verbose is True
    assert args.no_cache is False
    assert args.db is None


def test_cache_commands_parse():
    forced = build_parser().parse_args(
        ["fetch", "--chain", "newworld", "--store", "x", "--force", "--db", "cache.sqlite"]
    )
    assert forced.no_cache is True
    assert forced.db == "cache.sqlite"
    no_cache = build_parser().parse_args(
        ["fetch", "--chain", "newworld", "--store", "x", "--no-cache"]
    )
    assert no_cache.no_cache is True
    prices = build_parser().parse_args(
        ["prices", "--search", "banana", "--search", "apple", "--store", "A", "--store", "B", "--format", "json"]
    )
    assert prices.search == ["banana", "apple"]
    assert prices.stores == ["A", "B"]
    assert prices.date == "today"
    assert prices.department == "all"
    query = build_parser().parse_args(["query", "--limit", "0"])
    assert query.func.__name__ == "cmd_prices"
    status = build_parser().parse_args(["cache", "--json", "--days", "0", "--date", "today"])
    assert status.func.__name__ == "cmd_status"
    assert status.days == 0
    assert status.json is True
    compare = build_parser().parse_args(
        ["compare", "--search", "broccoli", "--store", "Browns Bay", "--fetch-if-missing"]
    )
    assert compare.search == ["broccoli"]
    assert compare.stores == ["Browns Bay"]
    assert compare.fetch_if_missing is True


def test_stores_and_update_flags():
    stores = build_parser().parse_args(["stores", "--live", "--region", "auckland", "--chain", "paknsave", "--json"])
    assert stores.live is True
    assert stores.region == "auckland"
    assert stores.chain == "paknsave"
    assert stores.json is True
    offline = build_parser().parse_args(["stores"])
    assert offline.live is False
    assert offline.region is None
    update = build_parser().parse_args(["update-stores"])
    assert update.output == "src/nzgrocery/stores/nz.json"
    assert update.no_cache is False
    forced = build_parser().parse_args(["stores", "--live", "--force"])
    assert forced.no_cache is True
    assert build_parser().parse_args(["stores", "--regions"]).regions is True


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "nz-grocery-prices" in capsys.readouterr().out


def test_stores_json_uses_the_bundled_list(capsys):
    assert main(["stores", "--json", "--chain", "paknsave"]) == 0
    payload = json.loads(capsys.readouterr().out)
    albany = next(store for store in payload if store["name"] == "PAK'nSAVE Albany")
    assert albany["id"] == "65defcf2-bc15-490e-a84f-1f13b769cd22"
    assert albany["region"] == "Auckland"
    assert all(store["chain"] == "paknsave" for store in payload)


def test_stores_region_filter_and_region_list(capsys):
    assert main(["stores", "--region", "auckland", "--chain", "paknsave", "--json"]) == 0
    auckland = json.loads(capsys.readouterr().out)
    assert auckland
    assert all(store["region"].casefold() == "auckland" for store in auckland)
    assert any(store["name"] == "PAK'nSAVE Albany" for store in auckland)

    assert main(["stores", "--region", "canterbury", "--json"]) == 0
    canterbury = json.loads(capsys.readouterr().out)
    assert canterbury
    assert all(store["region"].casefold() == "canterbury" for store in canterbury)
    assert {store["chain"] for store in canterbury} >= {"newworld"}

    assert main(["stores", "--regions", "--json"]) == 0
    regions = {row["region"].casefold(): row["stores"] for row in json.loads(capsys.readouterr().out)}
    assert "auckland" in regions
    assert "canterbury" in regions
    assert "waikato" in regions
    assert regions["auckland"] > regions["canterbury"]


def test_stores_table_lists_suburb(capsys):
    assert main(["stores", "--chain", "newworld"]) == 0
    text = capsys.readouterr().out
    assert "New World Browns Bay" in text
    assert "New World Long Bay" in text
    assert "chain" in text.splitlines()[0]


def test_bundled_suggestion_for_albany():
    hint = bundled_suggestion("paknsave", "Albany")
    assert "PAK'nSAVE Albany" in hint
    assert "65defcf2-bc15-490e-a84f-1f13b769cd22" in hint


def test_count_rows_level1_and_aisle():
    rows = [
        {"department": "produce", "category": "Fruit & Vegetables / Fruit / Bananas"},
        {"department": "produce", "category": "Fruit & Vegetables / Vegetables / Lettuce"},
        {"department": "meat", "category": "Meat, Poultry & Seafood / Beef / Mince"},
    ]
    counted = count_rows("paknsave", rows, "all")
    assert counted["level1_counts"]["produce"]["Fruit"] == 1
    assert counted["level1_counts"]["meat"]["Beef"] == 1


def test_department_choices_cover_both_catalogues():
    args = build_parser().parse_args(["fetch", "--chain", "newworld", "--store", "x", "--department", "meat"])
    assert args.department in FS_DEPARTMENTS
