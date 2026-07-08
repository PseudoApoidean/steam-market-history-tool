from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .filters import filter_by_games, unique_game_names
from .parser import load_history_json, parse_transactions
from .stats import summarize, summarize_by_game


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steam-market-history",
        description="Summarize lifetime profit/loss from a Steam Community Market history export.",
    )
    parser.add_argument("history_json", type=Path, help="Path to the market history JSON export")
    parser.add_argument(
        "--whitelist",
        help="Comma-separated game names to include (all others excluded)",
    )
    parser.add_argument(
        "--blacklist",
        help="Comma-separated game names to exclude",
    )
    parser.add_argument(
        "--by-game",
        action="store_true",
        help="Show a per-game breakdown in addition to the lifetime total",
    )
    parser.add_argument(
        "--list-games",
        action="store_true",
        help="List all game names found in the history and exit",
    )
    return parser


def _split_names(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [name.strip() for name in raw.split(",") if name.strip()]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    payload = load_history_json(args.history_json)
    transactions = parse_transactions(payload)

    if args.list_games:
        for name in unique_game_names(transactions):
            print(name)
        return 0

    transactions = filter_by_games(
        transactions,
        whitelist=_split_names(args.whitelist),
        blacklist=_split_names(args.blacklist),
    )

    if not transactions:
        print("No transactions match the given filters.", file=sys.stderr)
        return 1

    totals = summarize(transactions)
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
