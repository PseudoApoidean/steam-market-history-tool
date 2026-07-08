from __future__ import annotations

from collections.abc import Iterable

from .models import Transaction


def _normalize(name: str) -> str:
    return name.strip().casefold()


def filter_by_games(
    transactions: Iterable[Transaction],
    *,
    whitelist: Iterable[str] | None = None,
    blacklist: Iterable[str] | None = None,
) -> list[Transaction]:
    """Keep only transactions for the given games.

    Matching is case-insensitive and exact on the full game name (as it
    appears in Steam's history, e.g. "Counter-Strike 2"). If both are given,
    whitelist is applied first, then blacklist removes from what remains.
    """
    result = list(transactions)

    if whitelist is not None:
        allowed = {_normalize(name) for name in whitelist}
        result = [t for t in result if _normalize(t.game_name) in allowed]

    if blacklist is not None:
        blocked = {_normalize(name) for name in blacklist}
        result = [t for t in result if _normalize(t.game_name) not in blocked]

    return result


def unique_game_names(transactions: Iterable[Transaction]) -> list[str]:
    """All distinct game names present, sorted alphabetically.

    Useful for populating a whitelist/blacklist UI (CLI flag or future GUI
    checklist) without the caller needing to know the data ahead of time.
    """
    return sorted({t.game_name for t in transactions})
