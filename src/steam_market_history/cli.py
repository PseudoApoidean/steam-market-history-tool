from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .filters import FilterQueryError, filter_by_queries, parse_query, unique_game_names
from .parser import load_history_json, parse_transactions
from .stats import (
    CurrencyTotals,
    GameSummary,
    SeriesPoint,
    cumulative_series,
    summarize,
    summarize_by_game,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steam-market-history",
        description="Summarize lifetime profit/loss from a Steam Community Market history export.",
    )
    parser.add_argument("history_json", type=Path, help="Path to the market history JSON export")
    parser.add_argument(
        "--filter",
        dest="filters",
        action="append",
        metavar="QUERY",
        help=(
            "Filter transactions by a query, e.g. "
            "'game:CSGO||CS2||Counter-Strike 2 name:*Case'. Clauses (field:value, "
            "each starting a new field:) AND together; a value may contain spaces "
            "and runs up to the next clause; '||'-separated patterns within a "
            "clause's value OR together; patterns are case-insensitive globs; a "
            "leading '!' on a clause negates it (e.g. '!game:Rust'). Fields: "
            "game, name. Repeat --filter to OR multiple queries together."
        ),
    )
    parser.add_argument(
        "--by-game",
        action="store_true",
        help="Show a per-game breakdown in addition to the lifetime total (text output only)",
    )
    parser.add_argument(
        "--list-games",
        action="store_true",
        help="List all game names found in the history and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Output machine-readable JSON instead of human-readable text. Always "
            "'{\"ok\": true|false, ...}'; on success the payload is either "
            "{\"games\": [...]} (with --list-games) or {\"totals\": {...}, "
            "\"by_game\": {...}, \"series\": {...}} (--by-game has no effect in "
            "JSON mode, all three are always included; \"series\" is a running "
            "net-profit total per currency ordered oldest-transaction-first, "
            "keyed by currency the same as \"totals\"); on failure "
            "{\"error\": \"message\"}."
        ),
    )
    return parser


def _currency_totals_to_json(bucket: CurrencyTotals) -> dict[str, object]:
    return {
        "sold_total": str(bucket.sold_total),
        "sold_count": bucket.sold_count,
        "purchased_total": str(bucket.purchased_total),
        "purchased_count": bucket.purchased_count,
        "net_profit": str(bucket.net_profit),
    }


def _totals_to_json(totals: dict[str, CurrencyTotals]) -> dict[str, object]:
    return {currency: _currency_totals_to_json(bucket) for currency, bucket in totals.items()}


def _by_game_to_json(by_game: dict[str, GameSummary]) -> dict[str, object]:
    return {
        game_name: _totals_to_json(summary.totals_by_currency)
        for game_name, summary in by_game.items()
    }


def _series_point_to_json(point: SeriesPoint) -> dict[str, object]:
    return {
        "order_index": point.order_index,
        "acted_on": point.acted_on,
        "cumulative_net_profit": str(point.cumulative_net_profit),
    }


def _series_to_json(series: dict[str, list[SeriesPoint]]) -> dict[str, object]:
    return {
        currency: [_series_point_to_json(point) for point in points]
        for currency, points in series.items()
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        payload = load_history_json(args.history_json)
        transactions = parse_transactions(payload)
    except (OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"Error reading history: {exc}", file=sys.stderr)
        return 1

    if args.list_games:
        games = unique_game_names(transactions)
        if args.json:
            print(json.dumps({"ok": True, "games": games}))
        else:
            for name in games:
                print(name)
        return 0

    try:
        queries = [parse_query(query_text) for query_text in args.filters or []]
    except FilterQueryError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"Invalid --filter query: {exc}", file=sys.stderr)
        return 1

    transactions = filter_by_queries(transactions, queries)

    if not transactions:
        if args.json:
            print(json.dumps({"ok": True, "totals": {}, "by_game": {}, "series": {}}))
        else:
            print("No transactions match the given filters.", file=sys.stderr)
        return 1

    totals = summarize(transactions)

    if args.json:
        by_game = summarize_by_game(transactions)
        series = cumulative_series(transactions)
        print(
            json.dumps(
                {
                    "ok": True,
                    "totals": _totals_to_json(totals),
                    "by_game": _by_game_to_json(by_game),
                    "series": _series_to_json(series),
                }
            )
        )
        return 0

    print("Lifetime profit/loss:")
    for currency, bucket in sorted(totals.items()):
        print(
            f"  {currency}: sold {bucket.sold_total} ({bucket.sold_count} items), "
            f"purchased {bucket.purchased_total} ({bucket.purchased_count} items), "
            f"net {bucket.net_profit:+}"
        )

    if args.by_game:
        print("\nBy game:")
        by_game = summarize_by_game(transactions)
        for game_name in sorted(by_game):
            print(f"  {game_name}:")
            for currency, bucket in sorted(by_game[game_name].totals_by_currency.items()):
                print(
                    f"    {currency}: sold {bucket.sold_total} ({bucket.sold_count}), "
                    f"purchased {bucket.purchased_total} ({bucket.purchased_count}), "
                    f"net {bucket.net_profit:+}"
                )

    return 0
