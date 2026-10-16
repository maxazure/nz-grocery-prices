"""Offline tests for the local price cache and the read commands."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nzgrocery.cache import (
    default_db_path,
    latest_snapshot,
    list_snapshots,
    nz_date_of,
    nz_today,
    query_prices,
    resolve_store_offline,
)
from nzgrocery.cli import main
from nzgrocery.models import Store
from nzgrocery.output import dated_output_path, write_rows

NZ = ZoneInfo("Pacific/Auckland")
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=NZ)
STAMP = "2026-10-12T09:00:00+13:00"

ROW = {
    "fetched_at": STAMP,
    "chain": "newworld",
    "store_id": "773ad0a0-024e-46c5-a94b-df1cf86d25cc",
    "store": "New World Albany",
    "department": "produce",
    "category": "Fruit & Veg / Fruit",
    "name": "Bananas",
    "price_nzd": 3.49,
    "unit_or_size": "kg",
    "price_per": "$3.49 / 1kg",
    "product_url": "https://example.invalid/bananas",
    "raw_price_text": "$3.49",
    "product_id": "1",
}


def _row(**changes) -> dict:
    data = dict(ROW)
    data.update(changes)
    return data


def _freeze(monkeypatch, moment: datetime = NOW) -> None:
    monkeypatch.setattr("nzgrocery.cache.now_nz", lambda: moment)


def _install(monkeypatch, client) -> None:
    import nzgrocery.foodstuffs as foodstuffs

    monkeypatch.setattr(foodstuffs, "FoodstuffsClient", client)


class BoomClient:
    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("client should not be created")


def _fake(calls: list, rows_for):
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            calls.append(("init", args))

        def fetch(self, store_query, department):
            calls.append(("fetch", store_query, department))
            store = Store(
                chain="newworld",
                id="773ad0a0-024e-46c5-a94b-df1cf86d25cc",
                name="New World Albany",
                address="Albany",
            )
            return store, rows_for(department)

    return FakeClient


def _summary(capsys) -> dict:
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if line.startswith("{"))
    return json.loads(line)


def test_nz_dates_and_offsets():
    assert nz_date_of("2026-10-11T23:59:59+13:00") == date(2026, 10, 11)
    assert nz_date_of("2026-10-11T11:30:00+00:00") == date(2026, 10, 12)
    assert nz_date_of("2026-10-11T23:30:00") == date(2026, 10, 11)
    summer = datetime(2026, 1, 15, 12, tzinfo=NZ)
    winter = datetime(2026, 6, 15, 12, tzinfo=NZ)
    assert summer.utcoffset() == timedelta(hours=13)
    assert winter.utcoffset() == timedelta(hours=12)
    assert nz_date_of("2026-01-15T11:30:00+00:00") == date(2026, 1, 16)
    assert nz_date_of("2026-06-15T11:30:00+00:00") == date(2026, 6, 15)
    assert nz_date_of("2026-06-15T12:30:00+00:00") == date(2026, 6, 16)
    moment = datetime(2026, 10, 12, 0, 10, tzinfo=NZ)
    assert nz_today(moment) == date(2026, 10, 12)


def test_default_db_path_env_precedence(monkeypatch, tmp_path):
    monkeypatch.delenv("NZGROCERY_DB", raising=False)
    monkeypatch.setenv("NZGROCERY_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_db_path() == tmp_path / "data" / "prices.sqlite"

    monkeypatch.setenv("NZGROCERY_DB", str(tmp_path / "explicit.sqlite"))
    assert default_db_path() == tmp_path / "explicit.sqlite"

    monkeypatch.delenv("NZGROCERY_DB")
    monkeypatch.delenv("NZGROCERY_DATA")
    monkeypatch.setattr(sys, "platform", "linux")
    assert default_db_path() == tmp_path / "xdg" / "nz-grocery-prices" / "prices.sqlite"

    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert default_db_path() == (
        tmp_path / "Library" / "Application Support" / "nz-grocery-prices" / "prices.sqlite"
    )

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert default_db_path() == tmp_path / "local" / "nz-grocery-prices" / "prices.sqlite"


def test_missing_db_is_not_created(tmp_path):
    missing = tmp_path / "absent" / "prices.sqlite"
    assert list_snapshots(missing) == []
    assert query_prices(missing, chain="newworld") == ([], [])
    assert not missing.exists()
    assert resolve_store_offline("newworld", "No Such Store", missing) is None


def test_resolve_store_offline_bundled_then_cache():
    db = default_db_path()
    assert resolve_store_offline("newworld", "Albany", db) == ("773ad0a0-024e-46c5-a94b-df1cf86d25cc", "New World Albany")
    assert resolve_store_offline("paknsave", "Albany", db) == (
        "65defcf2-bc15-490e-a84f-1f13b769cd22",
        "PAK'nSAVE Albany",
    )
    write_rows(
        [
            _row(chain="paknsave", store_id="custom-1", store="PAK'nSAVE Customville North"),
            _row(chain="paknsave", store_id="custom-2", store="PAK'nSAVE Customville South"),
        ],
        "sqlite",
        db,
    )
    assert resolve_store_offline("paknsave", "custom-1", db) == ("custom-1", "PAK'nSAVE Customville North")
    assert resolve_store_offline("paknsave", "Customville", db) is None


def test_yesterday_nz_snapshot_is_not_today():
    db = default_db_path()
    write_rows([_row(fetched_at="2026-10-11T23:50:00+13:00")], "sqlite", db)
    moment = datetime(2026, 10, 12, 0, 10, tzinfo=NZ)
    assert latest_snapshot(db, "newworld", "773ad0a0-024e-46c5-a94b-df1cf86d25cc", "produce", date=nz_today(moment)) is None
    found = latest_snapshot(db, "newworld", "773ad0a0-024e-46c5-a94b-df1cf86d25cc", "produce", date=date(2026, 10, 11))
    assert found is not None
    assert found.rows == 1


def test_dated_filename_and_existing_file_skips_network(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    directory = default_db_path().parent
    path = dated_output_path("csv", "newworld", "New World Albany", "produce", NOW.date(), directory)
    write_rows([ROW], "csv", path)
    assert not default_db_path().exists()
    code = main(
        ["fetch", "--chain", "newworld", "--store", "Albany", "--department", "produce", "--format", "csv"]
    )
    assert code == 0
    summary = _summary(capsys)
    assert summary["cached"] is True
    assert summary["rows"] == 1
    assert summary["fetched_at"] == STAMP
    assert summary["output"] == str(path)
    assert summary["store_id"] == "773ad0a0-024e-46c5-a94b-df1cf86d25cc"
    assert not default_db_path().exists()


def test_sqlite_cache_hit_skips_network(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    write_rows([ROW], "sqlite", default_db_path())
    code = main(["fetch", "--chain", "newworld", "--store", "Albany", "--department", "produce"])
    assert code == 0
    summary = _summary(capsys)
    assert summary["cached"] is True
    assert summary["rows"] == 1
    assert summary["fetched_at"] == STAMP
    assert summary["db"] == str(default_db_path())
    assert summary["output"] == str(default_db_path())
    assert summary["snapshots"][0]["department"] == "produce"


def test_db_snapshot_exports_dated_file_without_network(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    write_rows([ROW], "sqlite", default_db_path())
    code = main(
        ["fetch", "--chain", "newworld", "--store", "Albany", "--department", "produce", "--format", "csv"]
    )
    assert code == 0
    summary = _summary(capsys)
    assert summary["cached"] is True
    exported = Path(summary["output"])
    assert exported.name == "newworld-new-world-albany-produce-2026-10-12.csv"
    assert exported.is_file()
    assert "Bananas" in exported.read_text(encoding="utf-8")


def test_explicit_output_uses_db_not_file_existence(monkeypatch, tmp_path):
    _freeze(monkeypatch)
    calls: list = []

    def rows_for(department):
        return [_row(name="Fresh bananas", product_id="9")]

    _install(monkeypatch, _fake(calls, rows_for))
    decoy = tmp_path / "explicit.csv"
    write_rows([ROW], "csv", decoy)
    code = main(
        [
            "fetch",
            "--chain",
            "newworld",
            "--store",
            "Albany",
            "--department",
            "produce",
            "--format",
            "csv",
            "--output",
            str(decoy),
        ]
    )
    assert code == 0
    assert ("fetch", "773ad0a0-024e-46c5-a94b-df1cf86d25cc", "produce") in calls
    assert "Fresh bananas" in decoy.read_text(encoding="utf-8")
    assert default_db_path().is_file()


@pytest.mark.parametrize("flag", ["--no-cache", "--force"])
def test_no_cache_and_force_refresh(monkeypatch, capsys, flag):
    _freeze(monkeypatch)
    monkeypatch.setenv("NZGROCERY_MIN_INTERVAL_MINUTES", "0")
    write_rows([ROW], "sqlite", default_db_path())
    calls: list = []
    _install(monkeypatch, _fake(calls, lambda department: [_row(name="Refreshed", price_nzd=1.11, product_id="2")]))
    code = main(["fetch", "--chain", "newworld", "--store", "Albany", "--department", "produce", flag])
    assert code == 0
    assert calls and calls[-1][0] == "fetch"
    summary = _summary(capsys)
    assert summary["cached"] is False
    assert "force_refused" not in summary


def test_no_cache_within_interval_is_refused(monkeypatch, capsys):
    moment = datetime(2026, 10, 12, 10, 0, tzinfo=NZ)
    _freeze(monkeypatch, moment)
    _install(monkeypatch, BoomClient)
    write_rows([_row(fetched_at="2026-10-12T09:52:00+13:00")], "sqlite", default_db_path())
    code = main(
        ["fetch", "--chain", "newworld", "--store", "Albany", "--department", "produce", "--no-cache"]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "refused" in captured.err
    summary = json.loads(captured.out)
    assert summary["force_refused"] is True
    assert summary["cached"] is True
    assert summary["retry_after_minutes"] == 2
    assert summary["rows"] == 1
    assert summary["fetched_at"] == "2026-10-12T09:52:00+13:00"


def test_no_cache_after_interval_calls_client(monkeypatch, capsys):
    _freeze(monkeypatch)
    write_rows([_row(fetched_at="2026-10-12T08:00:00+13:00")], "sqlite", default_db_path())
    calls: list = []
    _install(monkeypatch, _fake(calls, lambda department: [_row(name="Later", product_id="3")]))
    code = main(
        ["fetch", "--chain", "newworld", "--store", "Albany", "--department", "produce", "--force"]
    )
    assert code == 0
    assert ("fetch", "773ad0a0-024e-46c5-a94b-df1cf86d25cc", "produce") in calls
    summary = _summary(capsys)
    assert summary["cached"] is False
    assert summary["rows"] == 1


def test_department_all_fetches_only_missing_meat(monkeypatch, capsys):
    _freeze(monkeypatch)
    write_rows([ROW], "sqlite", default_db_path())
    calls: list = []

    def rows_for(department):
        return [_row(department=department, name="Beef mince", price_nzd=12.0, product_id="m")]

    _install(monkeypatch, _fake(calls, rows_for))
    code = main(["fetch", "--chain", "newworld", "--store", "Albany", "--department", "all"])
    assert code == 0
    assert [call for call in calls if call[0] == "fetch"] == [("fetch", "773ad0a0-024e-46c5-a94b-df1cf86d25cc", "meat")]
    summary = _summary(capsys)
    assert summary["cached"] is False
    assert summary["rows"] == 2
    by_dept = {item["department"]: item for item in summary["snapshots"]}
    assert by_dept["produce"]["cached"] is True
    assert by_dept["meat"]["cached"] is False


def test_yesterday_snapshot_does_not_count_as_today(monkeypatch):
    _freeze(monkeypatch, datetime(2026, 10, 12, 0, 10, tzinfo=NZ))
    write_rows([_row(fetched_at="2026-10-11T23:59:59+13:00")], "sqlite", default_db_path())
    calls: list = []
    _install(monkeypatch, _fake(calls, lambda department: [_row()]))
    assert main(["fetch", "--chain", "newworld", "--store", "Albany", "--department", "produce"]) == 0
    assert any(call[0] == "fetch" for call in calls)


def test_prices_filters_formats_and_exit_5(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    db = default_db_path()
    write_rows(
        [
            ROW,
            _row(name="Broccoli", price_nzd=2.50, product_id="b"),
            _row(department="meat", name="Beef mince", price_nzd=12.0, product_id="m"),
            _row(
                chain="paknsave",
                store_id="65defcf2-bc15-490e-a84f-1f13b769cd22",
                store="PAK'nSAVE Albany",
                name="Bananas",
                price_nzd=2.99,
                product_id="nw",
            ),
            _row(fetched_at="2026-10-11T09:00:00+13:00", name="Old bananas", price_nzd=9.0, product_id="old"),
        ],
        "sqlite",
        db,
    )
    assert main(
        ["prices", "--chain", "newworld", "--store", "Albany", "--search", "banana", "--format", "json"]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [row["name"] for row in payload] == ["Bananas"]
    assert payload[0]["fetched_at"] == STAMP
    assert payload[0]["price_nzd"] == 3.49

    assert main(
        [
            "prices",
            "--chain",
            "newworld",
            "--store",
            "Albany",
            "--department",
            "meat",
            "--format",
            "csv",
        ]
    ) == 0
    csv_out = capsys.readouterr().out
    assert "Beef mince" in csv_out
    assert "Bananas" not in csv_out.split("Beef", 1)[-1] or "Bananas" not in csv_out

    assert main(
        ["prices", "--store", "Albany", "--search", "banana", "--format", "table", "--limit", "1"]
    ) == 0
    table = capsys.readouterr().out
    assert "Bananas" in table
    assert table.count("Bananas") == 1

    assert main(
        ["prices", "--chain", "newworld", "--store", "Albany", "--date", "2026-10-11", "--format", "json"]
    ) == 0
    older = json.loads(capsys.readouterr().out)
    assert [row["name"] for row in older] == ["Old bananas"]

    assert main(
        ["prices", "--chain", "newworld", "--store", "Albany", "--date", "latest", "--search", "banana", "--format", "json"]
    ) == 0
    latest = json.loads(capsys.readouterr().out)
    assert [row["name"] for row in latest] == ["Bananas"]

    assert main(
        ["prices", "--chain", "newworld", "--store", "Albany", "--search", "dragonfruit", "--format", "json"]
    ) == 0
    empty = capsys.readouterr()
    assert empty.out.strip() == "[]"
    assert "no matching products" in empty.err

    code = main(["prices", "--chain", "newworld", "--store", "Albany", "--date", "2020-01-01"])
    missing = capsys.readouterr()
    assert code == 5
    assert "note:" not in missing.err
    assert "nz-grocery-prices fetch" in missing.err
    assert "newworld" in missing.err
    assert "Albany" in missing.err
    assert "--department" in missing.err


def test_partial_snapshot_notes_keep_rows_and_exit_0(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    write_rows([ROW], "sqlite", default_db_path())
    code = main(
        ["prices", "--store", "Albany", "--department", "produce", "--format", "json"]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert [row["name"] for row in json.loads(captured.out)] == ["Bananas"]
    assert "note:" not in captured.out
    assert captured.err.strip() == (
        'note: no local snapshot for PAK\'nSAVE Albany (produce) on 2026-10-12; '
        'fetch once with: nz-grocery-prices fetch --chain paknsave --store Albany --department produce'
    )

    code = main(
        ["prices", "--store", "Albany", "--department", "all", "--format", "json"]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert [row["name"] for row in json.loads(captured.out)] == ["Bananas"]
    assert [line for line in captured.err.splitlines() if line.startswith("note:")] == [
        'note: no local snapshot for PAK\'nSAVE Albany (produce) on 2026-10-12; '
        'fetch once with: nz-grocery-prices fetch --chain paknsave --store Albany --department produce',
        'note: no local snapshot for PAK\'nSAVE Albany (meat) on 2026-10-12; '
        'fetch once with: nz-grocery-prices fetch --chain paknsave --store Albany --department meat',
        'note: no local snapshot for New World Albany (meat) on 2026-10-12; '
        'fetch once with: nz-grocery-prices fetch --chain newworld --store Albany --department meat',
    ]

    code = main(
        [
            "prices",
            "--store",
            "Albany",
            "--department",
            "produce",
            "--search",
            "dragonfruit",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "[]"
    assert "no matching products" in captured.err
    assert "PAK'nSAVE Albany (produce)" in captured.err


def test_compare_partial_snapshot_notes_one_store(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    write_rows(
        [_row(name="Broccoli", price_nzd=2.50, product_id="b2")],
        "sqlite",
        default_db_path(),
    )
    code = main(
        ["compare", "--search", "broccoli", "--store", "Albany", "--department", "produce", "--json"]
    )
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert [item["chain"] for item in payload] == ["newworld"]
    assert captured.err.strip() == (
        'note: no local snapshot for PAK\'nSAVE Albany (produce) on 2026-10-12; '
        'fetch once with: nz-grocery-prices fetch --chain paknsave --store Albany --department produce'
    )

    code = main(["compare", "--search", "broccoli", "--store", "Albany", "--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert [item["chain"] for item in json.loads(captured.out)] == ["newworld"]
    assert captured.err.strip() == (
        'note: no local snapshot for PAK\'nSAVE Albany (all) on 2026-10-12; '
        'fetch once with: nz-grocery-prices fetch --chain paknsave --store Albany --department all'
    )

    code = main(
        ["compare", "--search", "broccoli", "--chain", "newworld", "--store", "Albany", "--json"]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "note:" not in captured.err
    assert json.loads(captured.out)[0]["chain"] == "newworld"

    code = main(["compare", "--search", "broccoli", "--store", "Albany", "--date", "2020-01-01"])
    captured = capsys.readouterr()
    assert code == 5
    assert "note:" not in captured.err
    assert "no local snapshot" in captured.err


def test_prices_missing_db_does_not_create_it(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    code = main(["prices", "--chain", "newworld", "--store", "Albany", "--department", "produce"])
    captured = capsys.readouterr()
    assert code == 5
    assert "nz-grocery-prices fetch --chain newworld" in captured.err
    assert "--fetch-if-missing" in captured.err
    assert not default_db_path().exists()


def test_fetch_if_missing_only_when_missing(monkeypatch, capsys):
    _freeze(monkeypatch)
    calls: list = []
    _install(monkeypatch, _fake(calls, lambda department: [_row(department=department, name="Bananas")]))
    code = main(
        [
            "prices",
            "--chain",
            "newworld",
            "--store",
            "Albany",
            "--department",
            "produce",
            "--fetch-if-missing",
            "--format",
            "json",
        ]
    )
    assert code == 0
    assert ("fetch", "773ad0a0-024e-46c5-a94b-df1cf86d25cc", "produce") in calls
    found = json.loads(capsys.readouterr().out)
    assert found[0]["name"] == "Bananas"
    calls.clear()
    _install(monkeypatch, BoomClient)
    assert main(
        [
            "prices",
            "--chain",
            "newworld",
            "--store",
            "Albany",
            "--department",
            "produce",
            "--fetch-if-missing",
            "--format",
            "json",
            "--search",
            "banana",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)[0]["store_id"] == "773ad0a0-024e-46c5-a94b-df1cf86d25cc"


def test_status_json(monkeypatch, capsys):
    _freeze(monkeypatch)
    write_rows([ROW, _row(department="meat", name="Beef", product_id="m")], "sqlite", default_db_path())
    assert main(["status", "--json", "--days", "7"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["db"] == str(default_db_path())
    assert payload["today"] == "2026-10-12"
    assert payload["snapshots"]
    assert all(item["today"] is True for item in payload["snapshots"])
    assert {item["department"] for item in payload["snapshots"]} == {"produce", "meat"}
    assert main(["cache", "--json", "--date", "2020-01-01"]) == 0
    assert json.loads(capsys.readouterr().out)["snapshots"] == []


def test_compare_picks_cheapest(monkeypatch, capsys):
    _freeze(monkeypatch)
    write_rows(
        [
            _row(name="Broccoli heads", price_nzd=4.50, product_id="b1"),
            _row(name="Broccoli", price_nzd=2.50, product_id="b2", price_per="$2.50 / 1kg"),
            _row(
                chain="paknsave",
                store_id="65defcf2-bc15-490e-a84f-1f13b769cd22",
                store="PAK'nSAVE Albany",
                name="Broccoli",
                price_nzd=3.00,
                product_id="b3",
            ),
        ],
        "sqlite",
        default_db_path(),
    )
    assert main(["compare", "--search", "broccoli", "--store", "Albany", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["price_nzd"] for item in payload] == [2.5, 3.0]
    newworld = next(item for item in payload if item["chain"] == "newworld")
    assert newworld["name"] == "Broccoli"
    assert newworld["matches"] == 2
    assert newworld["unit_or_size"] == "kg"


def test_stdout_cache_export(monkeypatch, capsys):
    _freeze(monkeypatch)
    _install(monkeypatch, BoomClient)
    write_rows([ROW], "sqlite", default_db_path())
    code = main(
        [
            "fetch",
            "--chain",
            "newworld",
            "--store",
            "Albany",
            "--department",
            "produce",
            "--format",
            "csv",
            "--output",
            "-",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Bananas" in captured.out
    summary = json.loads(captured.err)
    assert summary["cached"] is True
    assert summary["output"] == "-"
    assert summary["rows"] == 1
