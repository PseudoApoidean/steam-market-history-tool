from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from .acquisition import classify
from .filters import FilterQueryError, filter_by_queries, parse_query, unique_game_names
from .pairing import fifo_pairs
from .parser import load_history_json, parse_transactions
from .prices import PriceFileError, load_price_file
from .stats import (
    AcquisitionSummary,
    CurrencyTotals,
    GameSummary,
    ItemSummary,
    SeriesPoint,
    UnrealizedSummary,
    WinRateSummary,
    cumulative_series,
    summarize,
    summarize_acquisition,
    summarize_by_game,
    summarize_by_item,
    summarize_unrealized,
    summarize_win_rate,
)
from .unrealized import compute_unrealized


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
            "game, name, acquisition (values: drop, ambiguous, purchased - "
            "see --json's help for what these mean). Repeat --filter to OR "
            "multiple queries together."
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
        "--price-file",
        type=Path,
        metavar="PATH",
        help=(
            "Path to a JSON file of {item_name: current_price} for currently-held "
            "items, e.g. {\"Metal Facemask\": \"4.20\"}. This tool never makes "
            "network calls - if you want live prices, fetch them elsewhere "
            "(e.g. the steam-market-ledger GUI) and write them to a file in "
            "this shape first. Enables the \"unrealized\" JSON key; without "
            "it, unrealized gains aren't computed."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Output machine-readable JSON instead of human-readable text. Always "
            "'{\"ok\": true|false, ...}'; on success the payload is either "
            "{\"games\": [...]} (with --list-games) or {\"totals\": {...}, "
            "\"by_game\": {...}, \"by_item\": {...}, \"series\": {...}, "
            "\"acquisition\": {...}, \"win_rate\": {...}, \"unrealized\": {...}, "
            "\"unrealized_missing_prices\": [...]} (--by-game has no "
            "effect in JSON mode, all keys are always included; \"by_item\" "
            "is the same shape as \"by_game\" but keyed by item name "
            "instead, unranked - sort it by whichever currency/field "
            "matters for a most/least-profitable view; \"series\" is a "
            "running net-profit total per currency ordered "
            "oldest-transaction-first, each point's \"item_name\" is the "
            "transaction that produced it; \"acquisition\", keyed by currency "
            "like \"totals\", has \"confirmed_drop_revenue\"/"
            "\"confirmed_drop_count\" (sold items never purchased at all - "
            "exact, not a guess) and \"ambiguous_drop_revenue_min\"/\"_max\" "
            "(sold-more-than-purchased items, where which specific sales are "
            "drops can't be known - a real bound on the data, not a single "
            "guess) and \"ambiguous_count\"; \"win_rate\", keyed by "
            "currency, has \"profitable_count\"/\"losing_count\"/"
            "\"breakeven_count\" from FIFO-pairing each item's purchases to "
            "its sales by order_index (oldest with oldest) - a documented "
            "convention, not a recovered fact, see the README); \"unrealized\", "
            "keyed by currency, has \"held_count\"/\"current_value\"/"
            "\"gain_min\"/\"gain_max\" for currently-held items priced via "
            "--price-file - current_value is exact, gain_min/_max bound the "
            "cost-basis side the same way acquisition's ambiguous bounds do, "
            "since which specific held units remain can't be known; empty "
            "({}) if --price-file wasn't given; \"unrealized_missing_prices\" "
            "lists held item names with no entry in --price-file, so a caller "
            "can report an honest partial total; on failure "
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


def _by_item_to_json(by_item: dict[str, ItemSummary]) -> dict[str, object]:
    return {
        item_name: _totals_to_json(summary.totals_by_currency)
        for item_name, summary in by_item.items()
    }


def _series_point_to_json(point: SeriesPoint) -> dict[str, object]:
    return {
        "order_index": point.order_index,
        "acted_on": point.acted_on,
        "item_name": point.item_name,
        "cumulative_net_profit": str(point.cumulative_net_profit),
    }


def _series_to_json(series: dict[str, list[SeriesPoint]]) -> dict[str, object]:
    return {
        currency: [_series_point_to_json(point) for point in points]
        for currency, points in series.items()
    }


def _acquisition_summary_to_json(summary: AcquisitionSummary) -> dict[str, object]:
    return {
        "confirmed_drop_revenue": str(summary.confirmed_drop_revenue),
        "confirmed_drop_count": summary.confirmed_drop_count,
        "ambiguous_drop_revenue_min": str(summary.ambiguous_drop_revenue_min),
        "ambiguous_drop_revenue_max": str(summary.ambiguous_drop_revenue_max),
        "ambiguous_count": summary.ambiguous_count,
    }


def _acquisition_to_json(summaries: dict[str, AcquisitionSummary]) -> dict[str, object]:
    return {
        currency: _acquisition_summary_to_json(summary) for currency, summary in summaries.items()
    }


def _win_rate_summary_to_json(summary: WinRateSummary) -> dict[str, object]:
    return {
        "profitable_count": summary.profitable_count,
        "losing_count": summary.losing_count,
        "breakeven_count": summary.breakeven_count,
    }


def _win_rate_to_json(summaries: dict[str, WinRateSummary]) -> dict[str, object]:
    return {
        currency: _win_rate_summary_to_json(summary) for currency, summary in summaries.items()
    }


def _unrealized_summary_to_json(summary: UnrealizedSummary) -> dict[str, object]:
    return {
        "held_count": summary.held_count,
        "current_value": str(summary.current_value),
        "gain_min": str(summary.gain_min),
        "gain_max": str(summary.gain_max),
    }


def _unrealized_to_json(summaries: dict[str, UnrealizedSummary]) -> dict[str, object]:
    return {
        currency: _unrealized_summary_to_json(summary) for currency, summary in summaries.items()
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        payload = load_history_json(args.history_json)
        transactions = classify(parse_transactions(payload))
    except (OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"Error reading history: {exc}", file=sys.stderr)
        return 1

    prices: dict[str, Decimal] = {}
    if args.price_file is not None:
        try:
            prices = load_price_file(args.price_file)
        except PriceFileError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}))
            else:
                print(f"Error reading price file: {exc}", file=sys.stderr)
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
            print(
                json.dumps(
                    {
                        "ok": True,
                        "totals": {},
                        "by_game": {},
                        "by_item": {},
                        "series": {},
                        "acquisition": {},
                        "win_rate": {},
                        "unrealized": {},
                        "unrealized_missing_prices": [],
                    }
                )
            )
        else:
            print("No transactions match the given filters.", file=sys.stderr)
        return 1

    totals = summarize(transactions)

    if args.json:
        by_game = summarize_by_game(transactions)
        by_item = summarize_by_item(transactions)
        series = cumulative_series(transactions)
        acquisition_summary = summarize_acquisition(transactions)
        win_rate = summarize_win_rate(fifo_pairs(transactions))
        unrealized_summary: dict[str, UnrealizedSummary] = {}
        unrealized_missing_prices: list[str] = []
        if args.price_file is not None:
            unrealized_items, unrealized_missing_prices = compute_unrealized(transactions, prices)
            unrealized_summary = summarize_unrealized(unrealized_items)
        print(
            json.dumps(
                {
                    "ok": True,
                    "totals": _totals_to_json(totals),
                    "by_game": _by_game_to_json(by_game),
                    "by_item": _by_item_to_json(by_item),
                    "series": _series_to_json(series),
                    "acquisition": _acquisition_to_json(acquisition_summary),
                    "win_rate": _win_rate_to_json(win_rate),
                    "unrealized": _unrealized_to_json(unrealized_summary),
                    "unrealized_missing_prices": unrealized_missing_prices,
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
