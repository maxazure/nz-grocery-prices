"""Command line for listing stores and fetching produce or meat prices."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import sys
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

from nzgrocery import __version__
from nzgrocery.cache import (
    Snapshot,
    default_db_path,
    latest_fetched_at,
    latest_snapshot,
    list_snapshots,
    minutes_until_refresh,
    nz_date_of,
    nz_today,
    query_prices,
    resolve_store_offline,
    select_snapshots,
    snapshot_rows,
)
from nzgrocery.errors import AmbiguousStore, Blocked, NoRows, StoreNotFound, StoreVerificationError
from nzgrocery.models import CHAINS, PRICE_COLUMNS, Store
from nzgrocery.output import dated_output_path, read_rows, write_rows
from nzgrocery.reference import reference_status
from nzgrocery.stores import (
    build_store_list,
    filter_stores,
    load_bundled_stores,
    match_store,
    region_counts,
    write_store_list,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nz-grocery-prices",
        description=(
            "Fresh produce and meat prices from PAK'nSAVE and New World. "
            "Answers come from a local cache; a fetch runs only when today's snapshot is missing."
        ),
    )
    parser.add_argument("--version", action="version", version=f"nz-grocery-prices {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    stores = sub.add_parser("stores", help="List stores")
    stores.add_argument("--chain", choices=list(CHAINS), help="Limit to one chain")
    stores.add_argument(
        "--live",
        action="store_true",
        help="Use the live catalogue (cached for 7 days) instead of only the bundled list",
    )
    stores.add_argument(
        "--region",
        default=None,
        help="Region name, case-insensitive (auckland, canterbury, waikato, …). Default: all of New Zealand",
    )
    stores.add_argument(
        "--regions",
        action="store_true",
        help="List region names and how many stores each has",
    )
    stores.add_argument("--city", default=None, help="Filter by suburb, city, or address")
    stores.add_argument("--search", default=None, help="Filter by store name, suburb, or address")
    stores.add_argument(
        "--no-cache",
        "--force",
        action="store_true",
        dest="no_cache",
        help="Refresh cached live store lists instead of reusing them",
    )
    stores.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    stores.set_defaults(func=cmd_stores)

    fetch = sub.add_parser("fetch", help="Fetch one store")
    fetch.add_argument("--chain", required=True, choices=list(CHAINS))
    fetch.add_argument("--store", required=True, help="Store id or name substring")
    fetch.add_argument(
        "--department",
        default="produce",
        choices=("produce", "meat", "all"),
    )
    fetch.add_argument(
        "--format",
        default="sqlite",
        choices=("sqlite", "csv", "json", "jsonl"),
    )
    fetch.add_argument(
        "--output",
        default=None,
        help=(
            "File path, or - for stdout (csv/json/jsonl). "
            "For sqlite this is the database and replaces --db. "
            "Default: the cache database, or a dated file beside it"
        ),
    )
    fetch.add_argument(
        "--db",
        default=None,
        help="Cache database. Default: NZGROCERY_DB, NZGROCERY_DATA, or the platform data directory",
    )
    fetch.add_argument(
        "--no-cache",
        "--force",
        action="store_true",
        dest="no_cache",
        help=(
            "Refresh even when today's snapshot or dated file exists. "
            "Refused when the newest snapshot is younger than NZGROCERY_MIN_INTERVAL_MINUTES (default 10)"
        ),
    )
    fetch.add_argument("--dry-run", action="store_true", help="Fetch and parse, but do not write")
    fetch.add_argument("-v", "--verbose", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    prices = sub.add_parser(
        "prices",
        aliases=["query"],
        help="Read prices from the local cache",
    )
    prices.add_argument("--chain", choices=list(CHAINS))
    prices.add_argument("--store", action="append", dest="stores", help="Store id or name. Repeatable")
    prices.add_argument("--department", default="all", choices=("produce", "meat", "all"))
    prices.add_argument("--search", action="append", default=None, help="Product name substring. Repeatable (OR)")
    prices.add_argument(
        "--date",
        default="today",
        help="today (default), latest, or YYYY-MM-DD (Pacific/Auckland)",
    )
    prices.add_argument("--format", default="table", choices=("table", "json", "csv"))
    prices.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows. Default 50 for table, unlimited for json/csv. 0 = unlimited",
    )
    prices.add_argument("--sort", default="price", choices=("price", "name"))
    prices.add_argument("--db", default=None, help="Cache database")
    prices.add_argument(
        "--fetch-if-missing",
        action="store_true",
        help="Fetch departments that have no snapshot today (requires --chain and --store)",
    )
    prices.set_defaults(func=cmd_prices)

    status = sub.add_parser("status", aliases=["cache"], help="Show the local cache")
    status.add_argument("--chain", choices=list(CHAINS))
    status.add_argument("--store", default=None, help="Store id or name fragment")
    status.add_argument("--date", default=None, help="today or YYYY-MM-DD (Pacific/Auckland)")
    status.add_argument("--days", type=int, default=7, help="How many NZ days to include (0 = all). Default 7")
    status.add_argument("--json", action="store_true")
    status.add_argument("--db", default=None, help="Cache database")
    status.set_defaults(func=cmd_status)

    compare = sub.add_parser("compare", help="Cheapest local match per store")
    compare.add_argument("--search", action="append", required=True, help="Product name substring. Repeatable")
    compare.add_argument("--store", action="append", dest="stores", help="Store id or name. Repeatable")
    compare.add_argument("--chain", choices=list(CHAINS))
    compare.add_argument("--department", default="all", choices=("produce", "meat", "all"))
    compare.add_argument("--date", default="today", help="today (default), latest, or YYYY-MM-DD")
    compare.add_argument("--json", action="store_true")
    compare.add_argument("--db", default=None, help="Cache database")
    compare.add_argument(
        "--fetch-if-missing",
        action="store_true",
        help="Fetch missing today's snapshots for the named stores, one store at a time",
    )
    compare.set_defaults(func=cmd_compare)

    update = sub.add_parser("update-stores", help="Regenerate the bundled New Zealand store list")
    update.add_argument(
        "--output",
        default="src/nzgrocery/stores/nz.json",
        help="Where to write the nationwide list",
    )
    update.add_argument(
        "--no-cache",
        "--force",
        action="store_true",
        dest="no_cache",
        help="Refresh cached store lists",
    )
    update.set_defaults(func=cmd_update_stores)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except (StoreVerificationError, StoreNotFound, AmbiguousStore) as exc:
        print(str(exc), file=sys.stderr)
        print("Nothing saved.", file=sys.stderr)
        return 2
    except Blocked as exc:
        print(f"BLOCKED: {exc}. Nothing saved.", file=sys.stderr)
        return 3
    except NoRows as exc:
        print(str(exc), file=sys.stderr)
        print("Nothing saved.", file=sys.stderr)
        return 4


def cmd_stores(args: argparse.Namespace) -> int:
    region = args.region or "all"
    if args.live:
        stores = _live_stores(args.chain, force=bool(args.no_cache))
    else:
        stores = load_bundled_stores()
    if args.regions:
        listed = filter_stores(stores, chain=args.chain)
        _print_regions(listed, args.json)
        return 0
    stores = filter_stores(
        stores,
        chain=args.chain,
        region=region,
        city=args.city,
        search=args.search,
    )
    if args.json:
        json.dump([store.to_dict() for store in stores], sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(format_table(stores))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    if args.format == "sqlite" and args.output == "-":
        raise StoreVerificationError("sqlite output cannot be stdout; pass a file path")
    db_path = _fetch_db_path(args)
    departments = _department_list(args.department)
    today = nz_today()
    resolved = resolve_store_offline(args.chain, args.store, db_path)
    no_cache = bool(getattr(args, "no_cache", False))
    dated_file = _default_dated_file(args, resolved, today)

    if dated_file is not None and dated_file.is_file() and not no_cache:
        rows = read_rows(dated_file, args.format)
        _emit_fetch_summary(
            args,
            rows=rows,
            store_name=resolved[1] if resolved else args.store,
            store_id=resolved[0] if resolved else "",
            db_path=db_path,
            output_label=str(dated_file),
            cached_departments=set(departments),
            fetched=False,
            store=None,
        )
        return 0

    cached: dict[str, Snapshot] = {}
    if resolved is not None and not no_cache:
        for department in departments:
            snapshot = latest_snapshot(db_path, args.chain, resolved[0], department, date=today)
            if snapshot is not None:
                cached[department] = snapshot
        if len(cached) == len(departments):
            rows: list[dict] = []
            for department in departments:
                rows.extend(snapshot_rows(db_path, cached[department]))
            output_label = _export_cached_rows(args, rows, resolved[1], today, db_path)
            _emit_fetch_summary(
                args,
                rows=rows,
                store_name=resolved[1],
                store_id=resolved[0],
                db_path=db_path,
                output_label=output_label,
                cached_departments=set(departments),
                fetched=False,
                store=None,
            )
            return 0

    refused: dict[str, tuple[Snapshot, int]] = {}
    to_fetch = [department for department in departments if department not in cached]
    if no_cache and resolved is not None:
        to_fetch = []
        cached = {}
        for department in departments:
            snapshot = latest_snapshot(db_path, args.chain, resolved[0], department)
            wait = minutes_until_refresh(snapshot)
            if snapshot is not None and wait is not None:
                refused[department] = (snapshot, wait)
            else:
                to_fetch.append(department)
        if not to_fetch:
            retry = max(wait for _snapshot, wait in refused.values())
            rows = []
            for department in departments:
                rows.extend(snapshot_rows(db_path, refused[department][0]))
            if not rows and dated_file is not None and dated_file.is_file():
                rows = read_rows(dated_file, args.format)
            output_label = str(dated_file) if dated_file is not None and dated_file.is_file() else (
                str(db_path) if args.format == "sqlite" else _planned_output(args, resolved[1], today)
            )
            _warn_refresh_refused(resolved[1], refused, retry)
            _emit_fetch_summary(
                args,
                rows=rows,
                store_name=resolved[1],
                store_id=resolved[0],
                db_path=db_path,
                output_label=output_label,
                cached_departments=set(departments),
                fetched=False,
                store=None,
                force_refused=True,
                retry_after_minutes=retry,
            )
            return 0
        cached = {department: pair[0] for department, pair in refused.items()}

    if not to_fetch:
        return 0

    query = resolved[0] if resolved is not None else args.store
    print(bundled_suggestion(args.chain, args.store), file=sys.stderr)
    store, new_rows = _fetch_departments(args, query, departments, to_fetch)
    if not new_rows:
        raise NoRows("no rows parsed; nothing saved.")

    cached_rows: list[dict] = []
    for department in departments:
        if department in cached and department not in to_fetch:
            cached_rows.extend(snapshot_rows(db_path, cached[department]))
    all_rows = cached_rows + list(new_rows)
    store_name = store.name
    store_id = store.id
    output_label = None
    if not args.dry_run:
        if args.format == "sqlite":
            output_label = write_rows(new_rows, "sqlite", db_path)
        else:
            destination = _planned_output(args, store_name, today)
            output_label = write_rows(all_rows, args.format, destination)
            write_rows(new_rows, "sqlite", db_path)
    elif args.format != "sqlite":
        output_label = _planned_output(args, store_name, today)
    else:
        output_label = None

    _emit_fetch_summary(
        args,
        rows=all_rows,
        store_name=store_name,
        store_id=store_id,
        db_path=db_path,
        output_label=output_label,
        cached_departments={department for department in cached if department not in to_fetch},
        fetched=True,
        store=store,
        force_refused=bool(refused),
        retry_after_minutes=max((wait for _snapshot, wait in refused.values()), default=None),
    )
    return 0


def cmd_prices(args: argparse.Namespace) -> int:
    db_path = _read_db_path(args)
    parsed = _parse_date_mode(args.date)
    if parsed is None:
        return 2
    mode, on_date = parsed
    if args.fetch_if_missing:
        if not args.chain or not args.stores:
            print("--fetch-if-missing requires --chain and --store", file=sys.stderr)
            return 2
        for store_query in args.stores:
            code = _fetch_missing(args.chain, store_query, args.department, db_path, verbose=False)
            if code != 0:
                return code
    resolved, unresolved = _resolve_queries(args.chain, args.stores, db_path)
    if args.stores and not resolved and unresolved and not args.fetch_if_missing:
        _print_no_local(args.chain, unresolved, args.department, _date_label(mode, on_date))
        return 5
    if args.stores and args.chain and unresolved:
        _print_no_local(args.chain, unresolved, args.department, _date_label(mode, on_date))
        if not resolved:
            return 5
    store_pairs = [(chain, store_id) for chain, store_id, _name, _query in resolved]
    rows, snapshots = query_prices(
        db_path,
        chain=None if resolved else args.chain,
        stores=store_pairs or None,
        department=args.department,
        search=args.search,
        on_date=on_date,
        latest=mode == "latest",
        sort=args.sort,
        limit=_price_limit(args),
    )
    if snapshots and resolved:
        _note_partial_prices(resolved, snapshots, args.department, _date_label(mode, on_date))
    if not snapshots:
        queries = args.stores or ["<store>"]
        chain = args.chain
        _print_no_local(chain, queries, args.department, _date_label(mode, on_date))
        return 5
    if not rows:
        print("no matching products", file=sys.stderr)
        if args.format == "json":
            sys.stdout.write("[]\n")
        return 0
    _write_price_rows(rows, args.format)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    db_path = _read_db_path(args)
    today = nz_today()
    exact: date | None = None
    since: date | None = None
    if args.date:
        if args.date == "today":
            exact = today
        else:
            try:
                exact = date.fromisoformat(args.date)
            except ValueError:
                print(f"invalid date {args.date!r}; use today or YYYY-MM-DD", file=sys.stderr)
                return 2
    elif args.days and args.days > 0:
        since = today - timedelta(days=args.days - 1)
    store_id = None
    if args.store and args.chain:
        match = resolve_store_offline(args.chain, args.store, db_path)
        if match is not None:
            store_id = match[0]
    snapshots = list_snapshots(
        db_path,
        chain=args.chain,
        store_id=store_id,
        date=exact,
        since=since,
    )
    if args.store and store_id is None:
        needle = args.store.casefold()
        snapshots = [
            snap
            for snap in snapshots
            if snap.store_id.casefold() == needle or needle in snap.store.casefold()
        ]
    payload = {
        "db": str(db_path),
        "today": today.isoformat(),
        "snapshots": [snap.to_dict(today=today) for snap in snapshots],
        "reference": reference_status(now=None),
    }
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    print(f"db: {db_path}")
    print(f"today: {today.isoformat()}")
    if not snapshots:
        print("no snapshots")
    else:
        _write_status_table(snapshots, today)
    _print_reference(payload["reference"])
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    db_path = _read_db_path(args)
    parsed = _parse_date_mode(args.date)
    if parsed is None:
        return 2
    mode, on_date = parsed
    targets = _compare_targets(args, db_path)
    if args.fetch_if_missing:
        if not args.stores:
            print("--fetch-if-missing requires --store", file=sys.stderr)
            return 2
        seen: set[tuple[str, str]] = set()
        for chain, store_id, _name, query in targets:
            if (chain, store_id) in seen:
                continue
            seen.add((chain, store_id))
            code = _fetch_missing(chain, query, args.department, db_path, verbose=False)
            if code != 0:
                return code
        if args.chain:
            for query in args.stores:
                if any(item[0] == args.chain and item[3] == query for item in targets):
                    continue
                code = _fetch_missing(args.chain, query, args.department, db_path, verbose=False)
                if code != 0:
                    return code
        targets = _compare_targets(args, db_path)
    stores = [(chain, store_id) for chain, store_id, _name, _query in targets] or None
    if args.stores and not stores:
        _print_no_local(args.chain, list(args.stores), args.department, _date_label(mode, on_date))
        return 5
    snapshots = select_snapshots(
        db_path,
        chain=None if stores else args.chain,
        stores=stores,
        department=args.department,
        on_date=on_date,
        latest=mode == "latest",
    )
    if not snapshots:
        hint_stores = list(args.stores) if args.stores else ["<store>"]
        _print_no_local(args.chain, hint_stores, args.department, _date_label(mode, on_date))
        return 5
    if targets:
        _note_partial_compare(targets, snapshots, args.department, _date_label(mode, on_date))
    results = _cheapest_matches(db_path, snapshots, args.search)
    if not results:
        print("no matching products", file=sys.stderr)
        if args.json:
            sys.stdout.write("[]\n")
        return 0
    if args.json:
        json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    _write_compare_table(results)
    return 0


def _department_list(department: str) -> list[str]:
    if department == "all":
        return ["produce", "meat"]
    return [department]


def _fetch_db_path(args: argparse.Namespace) -> Path:
    if args.format == "sqlite" and args.output not in (None, "-"):
        return Path(args.output)
    if getattr(args, "db", None):
        return Path(args.db)
    return default_db_path()


def _read_db_path(args: argparse.Namespace) -> Path:
    if getattr(args, "db", None):
        return Path(args.db)
    return default_db_path()


def _default_dated_file(args: argparse.Namespace, resolved: tuple[str, str] | None, today: date) -> Path | None:
    if args.format not in {"csv", "json", "jsonl"} or args.output is not None or resolved is None:
        return None
    return dated_output_path(
        args.format,
        args.chain,
        resolved[1],
        args.department,
        today,
        default_db_path().parent,
    )


def _planned_output(args: argparse.Namespace, store_name: str, today: date) -> str:
    if args.output is not None:
        return args.output
    return str(
        dated_output_path(
            args.format,
            args.chain,
            store_name,
            args.department,
            today,
            default_db_path().parent,
        )
    )


def _export_cached_rows(
    args: argparse.Namespace,
    rows: list[dict],
    store_name: str,
    today: date,
    db_path: Path,
) -> str:
    """Write a cached snapshot to the requested export. SQLite is already the cache."""
    if args.format == "sqlite":
        return str(db_path)
    destination = _planned_output(args, store_name, today)
    if args.dry_run:
        return destination
    return write_rows(rows, args.format, destination)


def _fetch_departments(
    args: argparse.Namespace,
    query: str,
    departments: list[str],
    to_fetch: list[str],
) -> tuple[Store, list[dict]]:
    from nzgrocery.foodstuffs import FoodstuffsClient

    client = FoodstuffsClient(args.chain, verbose=args.verbose)
    if to_fetch == departments:
        return client.fetch(query, args.department)
    store: Store | None = None
    rows: list[dict] = []
    for department in to_fetch:
        store, part = client.fetch(query, department)
        rows.extend(part)
    if store is None:
        raise NoRows("no rows parsed; nothing saved.")
    return store, rows


def _fetch_missing(chain: str, store_query: str, department: str, db_path: Path, *, verbose: bool) -> int:
    """Fetch only what today is missing, using the same path as ``nz-grocery-prices fetch``."""
    namespace = argparse.Namespace(
        chain=chain,
        store=store_query,
        department=department,
        format="sqlite",
        output=None,
        db=str(db_path),
        dry_run=False,
        verbose=verbose,
        no_cache=False,
        summary_on_stderr=True,
    )
    return cmd_fetch(namespace)


def _warn_refresh_refused(store_name: str, refused: dict[str, tuple[Snapshot, int]], retry: int) -> None:
    departments = ", ".join(refused)
    print(
        f"refresh refused for {store_name} ({departments}): newest snapshot is younger than "
        f"NZGROCERY_MIN_INTERVAL_MINUTES. Retry after {retry} minutes.",
        file=sys.stderr,
    )


def _emit_fetch_summary(
    args: argparse.Namespace,
    *,
    rows: list[dict],
    store_name: str,
    store_id: str,
    db_path: Path,
    output_label: str | None,
    cached_departments: set[str],
    fetched: bool,
    store: Store | None,
    force_refused: bool = False,
    retry_after_minutes: int | None = None,
) -> None:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("department") or ""), []).append(row)
    snapshots = []
    for department, items in grouped.items():
        snapshots.append(
            {
                "department": department,
                "fetched_at": latest_fetched_at([item.get("fetched_at") for item in items]),
                "rows": len(items),
                "cached": department in cached_departments,
            }
        )
    summary: dict = {
        "cached": not fetched,
        "chain": args.chain,
        "store": store_name,
        "store_id": store_id,
        "department": args.department,
        "rows": len(rows),
        "fetched_at": latest_fetched_at([row.get("fetched_at") for row in rows]),
        "snapshots": snapshots,
        "db": str(db_path),
        "output": output_label,
        "dry_run": bool(args.dry_run),
    }
    if force_refused:
        summary["force_refused"] = True
        summary["retry_after_minutes"] = retry_after_minutes
    if rows:
        summary.update(count_rows(args.chain, rows, args.department))
    wrote_stdout = output_label == "-" and not args.dry_run
    to_stderr = wrote_stdout or bool(getattr(args, "summary_on_stderr", False))
    print(json.dumps(summary, ensure_ascii=False), file=sys.stderr if to_stderr else sys.stdout, flush=True)


def _parse_date_mode(value: str) -> tuple[str, date | None] | None:
    if value == "latest":
        return "latest", None
    if value == "today":
        return "today", nz_today()
    try:
        return "date", date.fromisoformat(value)
    except ValueError:
        print(f"invalid date {value!r}; use today, latest, or YYYY-MM-DD", file=sys.stderr)
        return None


def _date_label(mode: str, on_date: date | None) -> str:
    if mode == "latest":
        return "the latest snapshot"
    if on_date is not None:
        return on_date.isoformat()
    return mode


def _price_limit(args: argparse.Namespace) -> int:
    if args.limit is None:
        return 50 if args.format == "table" else 0
    return args.limit


def _resolve_queries(
    chain: str | None,
    stores: list[str] | None,
    db_path: Path,
) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """Return ``([(chain, store_id, store_name, query), ...], unresolved)``."""
    if not stores:
        return [], []
    chains = [chain] if chain else list(CHAINS)
    resolved: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    unresolved: list[str] = []
    for query in stores:
        found = False
        for item_chain in chains:
            match = resolve_store_offline(item_chain, query, db_path)
            if match is None:
                continue
            pair = (item_chain, match[0])
            if pair not in seen:
                seen.add(pair)
                resolved.append((item_chain, match[0], match[1], query))
            found = True
        if not found:
            unresolved.append(query)
    return resolved, unresolved


def _compare_targets(
    args: argparse.Namespace,
    db_path: Path,
) -> list[tuple[str, str, str, str]]:
    """``(chain, store_id, store_name, query)`` for each offline match."""
    if not args.stores:
        return []
    chains = [args.chain] if args.chain else list(CHAINS)
    targets: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for query in args.stores:
        for chain in chains:
            match = resolve_store_offline(chain, query, db_path)
            if match is None or (chain, match[0]) in seen:
                continue
            seen.add((chain, match[0]))
            targets.append((chain, match[0], match[1], query))
    return targets


def _quote_store(value: str) -> str:
    """Shell-quote a store query, using double quotes for the common spaced name."""
    quoted = shlex.quote(value)
    if quoted.startswith("'") and quoted.endswith("'") and "'" not in value:
        return f'"{value}"'
    return quoted


def _note_missing(chain: str, store_name: str, query: str, department: str, when: str) -> None:
    print(
        f"note: no local snapshot for {store_name} ({department}) on {when}; "
        f"fetch once with: nz-grocery-prices fetch --chain {chain} --store {_quote_store(query)} "
        f"--department {department}",
        file=sys.stderr,
    )


def _note_partial_prices(
    resolved: list[tuple[str, str, str, str]],
    snapshots: list[Snapshot],
    department: str,
    when: str,
) -> None:
    """One stderr note per resolved store (and department, when ``all``) that has no snapshot.

    Printed only when at least one requested target did have data, so the
    all-missing path can keep the exit-5 message.
    """
    departments = _department_list(department)
    present = {(snap.chain, snap.store_id, snap.department) for snap in snapshots}
    found = 0
    missing: list[tuple[str, str, str, str]] = []
    for chain, store_id, store_name, query in resolved:
        for item_department in departments:
            if (chain, store_id, item_department) in present:
                found += 1
            else:
                missing.append((chain, store_name, query, item_department))
    if not found or not missing:
        return
    for chain, store_name, query, item_department in missing:
        _note_missing(chain, store_name, query, item_department, when)


def _note_partial_compare(
    targets: list[tuple[str, str, str, str]],
    snapshots: list[Snapshot],
    department: str,
    when: str,
) -> None:
    """One stderr note per resolved chain+store with no snapshot on the selected date.

    ``--department all`` is a single target per store. Notes are skipped when
    every requested store is missing.
    """
    present = {(snap.chain, snap.store_id) for snap in snapshots}
    missing = [item for item in targets if (item[0], item[1]) not in present]
    if not missing or len(missing) == len(targets):
        return
    for chain, _store_id, store_name, query in missing:
        _note_missing(chain, store_name, query, department, when)


def _print_no_local(chain: str | None, stores: list[str], department: str, when: str) -> None:
    chain_text = chain or "<chain>"
    store_text = ", ".join(stores) if stores else "<store>"
    commands = []
    for store in stores or ["<store>"]:
        store_arg = store if store == "<store>" else shlex.quote(store)
        commands.append(
            f"nz-grocery-prices fetch --chain {chain_text} --store {store_arg} --department {department}"
        )
    extra = ""
    if chain and stores and "<store>" not in stores:
        store_flags = "".join(f" --store {shlex.quote(store)}" for store in stores)
        extra = (
            f" Or: nzgrocery prices --chain {chain}{store_flags} "
            f"--department {department} --fetch-if-missing"
        )
    print(
        f"no local snapshot for {chain_text} {store_text} department {department} on {when}. "
        f"Fetch it with: {'; '.join(commands)}.{extra}",
        file=sys.stderr,
    )


def _write_price_rows(rows: list[dict], fmt: str) -> None:
    if fmt == "json":
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return
    if fmt == "csv":
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(PRICE_COLUMNS), lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in PRICE_COLUMNS})
        sys.stdout.write(buffer.getvalue())
        return
    sys.stdout.write(_format_price_table(rows))


def _format_price_table(rows: list[dict]) -> str:
    headers = ("date", "chain", "store", "department", "name", "price", "unit/size", "price_per", "raw")
    body = []
    for row in rows:
        try:
            day = nz_date_of(str(row.get("fetched_at") or ""))
            day_text = day.isoformat()
        except ValueError:
            day_text = ""
        try:
            price = f"${float(row.get('price_nzd')):.2f}"
        except (TypeError, ValueError):
            price = ""
        body.append(
            (
                day_text,
                str(row.get("chain") or ""),
                _clip(row.get("store") or "", 28),
                str(row.get("department") or ""),
                _clip(row.get("name") or "", 42),
                price,
                _clip(row.get("unit_or_size") or "", 16),
                _clip(row.get("price_per") or "", 18),
                _clip(row.get("raw_price_text") or "", 36),
            )
        )
    return _render_cells(headers, body)


def _write_status_table(snapshots: list[Snapshot], today: date) -> None:
    headers = ("date", "today", "chain", "store", "store_id", "department", "rows", "fetched_at")
    body = [
        (
            snap.nz_date.isoformat(),
            "yes" if snap.nz_date == today else "",
            snap.chain,
            snap.store,
            snap.store_id,
            snap.department,
            str(snap.rows),
            snap.fetched_at,
        )
        for snap in snapshots
    ]
    sys.stdout.write(_render_cells(headers, body))


def _cheapest_matches(db_path: Path, snapshots: list[Snapshot], terms: list[str]) -> list[dict]:
    loaded = [(snap, snapshot_rows(db_path, snap)) for snap in snapshots]
    results = []
    for term in terms:
        needle = term.casefold()
        for snap, rows in loaded:
            matches = [row for row in rows if needle in (row.get("name") or "").casefold()]
            if not matches:
                continue
            matches.sort(key=lambda row: (float(row.get("price_nzd") or 0), row.get("name") or ""))
            best = matches[0]
            results.append(
                {
                    "search": term,
                    "date": snap.nz_date.isoformat(),
                    "chain": snap.chain,
                    "store": snap.store,
                    "store_id": snap.store_id,
                    "department": snap.department,
                    "fetched_at": snap.fetched_at,
                    "matches": len(matches),
                    "name": best.get("name"),
                    "price_nzd": best.get("price_nzd"),
                    "unit_or_size": best.get("unit_or_size"),
                    "price_per": best.get("price_per"),
                }
            )
    results.sort(key=lambda item: (item["search"].casefold(), float(item["price_nzd"] or 0), item["store"]))
    return results


def _write_compare_table(results: list[dict]) -> None:
    headers = ("search", "date", "chain", "store", "department", "name", "price", "unit/size", "price_per", "matches")
    body = []
    for item in results:
        try:
            price = f"${float(item['price_nzd']):.2f}"
        except (TypeError, ValueError):
            price = ""
        body.append(
            (
                item["search"],
                item["date"],
                item["chain"],
                item["store"],
                item["department"],
                _clip(item.get("name") or "", 42),
                price,
                _clip(item.get("unit_or_size") or "", 16),
                _clip(item.get("price_per") or "", 18),
                str(item["matches"]),
            )
        )
    sys.stdout.write(_render_cells(headers, body))


def _clip(text: str, width: int) -> str:
    text = str(text)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _render_cells(headers: tuple[str, ...], body: list[tuple[str, ...]]) -> str:
    widths = [len(header) for header in headers]
    for row in body:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(cells)).rstrip()

    lines = [line(headers), line(tuple("-" * width for width in widths))]
    lines.extend(line(row) for row in body)
    return "\n".join(lines) + "\n"


def cmd_update_stores(args: argparse.Namespace) -> int:
    from nzgrocery.foodstuffs import FoodstuffsClient

    force = bool(getattr(args, "no_cache", False))
    paknsave = FoodstuffsClient("paknsave").fetch_store_payload(force=force)
    newworld = FoodstuffsClient("newworld").fetch_store_payload(force=force)
    stores = build_store_list(paknsave, newworld)
    write_store_list(Path(args.output), stores)
    counts = {chain: sum(s.chain == chain for s in stores) for chain in CHAINS}
    print(json.dumps({"output": args.output, "stores": len(stores), "counts": counts}))
    return 0


def bundled_suggestion(chain: str, query: str) -> str:
    """Hint from the bundled nationwide list. The live list is used when this misses."""
    bundled = [store for store in load_bundled_stores() if store.chain == chain]
    try:
        match = match_store(bundled, query)
    except StoreNotFound:
        return (
            f"bundled NZ {chain} list has no match for {query!r}; "
            "the live list is authoritative"
        )
    except AmbiguousStore as exc:
        return f"bundled NZ list: {exc} The live list is authoritative."
    return (
        f"bundled NZ list: {match.name} (id={match.id}, region={match.region}). "
        "Using its store ID for the catalogue request."
    )


def count_rows(chain: str, rows: list[dict], department: str) -> dict:
    field = "level1_counts"

    def tally(subset: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in subset:
            category = row.get("category") or ""
            parts = category.split(" / ")
            if len(parts) <= 1:
                continue
            key = parts[1]
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts

    if department == "all":
        grouped = {
            name: tally([row for row in rows if row.get("department") == name])
            for name in ("produce", "meat")
        }
        return {field: grouped}
    return {field: tally(rows)}


def format_table(stores: list[Store]) -> str:
    headers = ("chain", "region", "id", "name", "suburb")
    body = []
    for store in stores:
        body.append(
            (
                store.chain,
                store.region or "",
                store.id,
                store.name,
                store.suburb or store.address or "",
            )
        )
    return _render_cells(headers, body)


def _print_regions(stores: list[Store], as_json: bool) -> None:
    rows = region_counts(stores)
    if as_json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return
    body = [(row["region"], str(row["stores"])) for row in rows]
    sys.stdout.write(_render_cells(("region", "stores"), body))


def _print_reference(rows: list[dict]) -> None:
    print("reference:")
    if not rows:
        print("  none")
        return
    for row in rows:
        age = row.get("age")
        age_text = "unknown" if age is None else _format_age(int(age))
        expired = "yes" if row.get("expired") else "no"
        chain = f" chain={row['chain']}" if row.get("chain") else ""
        print(
            f"  {row['kind']}{chain}  file={row['file']}  fetched_at={row.get('fetched_at')}  "
            f"age={age_text}  ttl={row.get('ttl')}d  expired={expired}"
        )


def _format_age(seconds: int) -> str:
    if seconds < 0:
        return "0s"
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 36 * 3600:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _live_stores(chain: str | None, *, force: bool = False) -> list[Store]:
    from nzgrocery.foodstuffs import FoodstuffsClient

    stores = []
    for name in ((chain,) if chain else CHAINS):
        stores.extend(FoodstuffsClient(name).list_stores(force=force))
    return stores
