"""Reusable core for analyzing Steam Community Market history exports.

This package is intentionally presentation-agnostic: `parser`, `filters`,
and `stats` operate on plain data (dicts in, dataclasses out) with no
dependency on argparse or stdout. `cli` is the first consumer of this
core, not the core itself — a future GUI frontend should import from here
directly rather than shelling out to or duplicating the CLI.
"""

from .filters import (
    Clause,
    FilterQueryError,
    Query,
    filter_by_queries,
    match_query,
    parse_query,
    unique_game_names,
)
from .models import Action, Transaction
from .parser import HistoryParseError, load_history_json, parse_transactions
from .stats import CurrencyTotals, GameSummary, summarize, summarize_by_game

__all__ = [
    "Action",
    "Clause",
    "CurrencyTotals",
    "FilterQueryError",
    "GameSummary",
    "HistoryParseError",
    "Query",
    "Transaction",
    "filter_by_queries",
    "load_history_json",
    "match_query",
    "parse_query",
    "parse_transactions",
    "summarize",
    "summarize_by_game",
    "unique_game_names",
]
