"""Command line entry point for the Solana growth tracker."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .aggregate import DEFAULT_EXCLUDED_CATEGORIES, collect
from .defillama import DefiLlama
from .export import append_history, write_csv, write_json, write_markdown
from .models import Protocol, Snapshot
from .render import (
    markdown_report,
    render_growth,
    render_overview,
    render_tvl,
    render_volume,
)

DEFAULT_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "soltracker")

# Shared flags are declared with SUPPRESS so a subparser never clobbers a value
# the user passed before the subcommand; defaults are filled in after parsing.
DEFAULTS = {
    "limit": 20,
    "history": 60,
    "min_tvl": 1_000_000.0,
    "min_volume": 1_000_000.0,
    "category": [],
    "exclude_category": list(DEFAULT_EXCLUDED_CATEGORIES),
    "include_small": False,
    "cache_dir": DEFAULT_CACHE,
    "cache_ttl": 900,
    "no_cache": False,
    "json": False,
    "out": "web/data",
    "report": "REPORT.md",
    "no_history_log": False,
}


def _common_flags() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument("--limit", type=int, help="rows per table (default: 20)")
    common.add_argument(
        "--history",
        type=int,
        help="fetch TVL history for the N largest protocols, enabling 30d/90d changes (default: 60)",
    )
    common.add_argument("--min-tvl", type=float, help="ignore protocols below this Solana TVL")
    common.add_argument("--min-volume", type=float, help="...unless 24h volume clears this")
    common.add_argument("--category", action="append", help="filter by category (repeatable)")
    common.add_argument(
        "--exclude-category",
        action="append",
        help="drop a category entirely (default: {})".format(", ".join(DEFAULT_EXCLUDED_CATEGORIES)),
    )
    common.add_argument(
        "--include-small",
        action="store_true",
        help="let sub-threshold protocols onto the growth board",
    )
    common.add_argument("--cache-dir", help="where to cache API responses")
    common.add_argument("--cache-ttl", type=int, help="seconds to reuse cached API responses")
    common.add_argument("--no-cache", action="store_true", help="bypass the response cache")
    common.add_argument("--json", action="store_true", help="print the raw snapshot as JSON")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_flags()
    parser = argparse.ArgumentParser(
        prog="soltracker",
        parents=[common],
        description="Track TVL, volume and fee growth across the Solana ecosystem.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("overview", parents=[common], help="chain summary plus the headline tables (default)")
    sub.add_parser("tvl", parents=[common], help="largest protocols by Solana TVL")
    sub.add_parser("volume", parents=[common], help="highest volume protocols")
    sub.add_parser("growth", parents=[common], help="fastest growing protocols by momentum score")

    export = sub.add_parser(
        "export", parents=[common], help="write snapshot.json, report.md, CSV and history log"
    )
    export.add_argument("--out", help="directory for dashboard data (default: web/data)")
    export.add_argument("--report", help="path for the Markdown report")
    export.add_argument("--no-history-log", action="store_true", help="skip appending to history.jsonl")

    return parser


def _filter(protocols: List[Protocol], categories: List[str]) -> List[Protocol]:
    if not categories:
        return protocols
    wanted = {c.lower() for c in categories}
    return [p for p in protocols if p.category.lower() in wanted]


def _build_snapshot(args: argparse.Namespace) -> Snapshot:
    client = DefiLlama(
        cache_dir=None if args.no_cache else args.cache_dir,
        cache_ttl=0 if args.no_cache else args.cache_ttl,
    )
    return collect(
        client,
        history_limit=max(0, args.history),
        min_tvl=args.min_tvl,
        min_volume=args.min_volume,
        exclude_categories=args.exclude_category,
    )


def _run_export(snapshot: Snapshot, args: argparse.Namespace) -> None:
    written = [
        write_json(snapshot, os.path.join(args.out, "snapshot.json")),
        write_csv(snapshot, os.path.join(args.out, "protocols.csv")),
        write_markdown(markdown_report(snapshot, limit=max(args.limit, 25)), args.report),
    ]
    if not args.no_history_log:
        written.append(append_history(snapshot, os.path.join(args.out, "history.jsonl")))
    for path in written:
        print("wrote {}".format(path))


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    for name, value in DEFAULTS.items():
        if getattr(args, name, None) is None:
            setattr(args, name, value)
    command = args.command or "overview"

    try:
        snapshot = _build_snapshot(args)
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean CLI error
        print("error: {}".format(exc), file=sys.stderr)
        return 1

    if args.json:
        json.dump(snapshot.to_dict(include_history=False), sys.stdout, indent=2)
        print()
        return 0

    if command == "export":
        _run_export(snapshot, args)
        return 0

    protocols = _filter(snapshot.protocols, args.category)

    if command == "overview":
        print(render_overview(snapshot))
        print("\nTop protocols by TVL\n")
        print(render_tvl(protocols, args.limit))
        print("\nFastest growing\n")
        print(render_growth(protocols, args.limit, args.include_small))
    elif command == "tvl":
        print(render_tvl(protocols, args.limit))
    elif command == "volume":
        print(render_volume(protocols, args.limit))
    elif command == "growth":
        print(render_growth(protocols, args.limit, args.include_small))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
