from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .models import Action, Transaction
from .money import parse_price

_ROW_SPLIT = "market_listing_row market_recent_listing_row"
_PRICE_RE = re.compile(r'market_listing_price">\s*([^<]+?)\s*</span>')
_DATES_RE = re.compile(r'market_listing_listed_date can_combine">\s*([^<]+?)\s*</div>')
_ITEM_RE = re.compile(r'class="market_listing_item_name"[^>]*>([^<]*)<')
_GAME_RE = re.compile(r'class="market_listing_game_name">([^<]*)<')
_ACTION_RE = re.compile(r'class="market_listing_listed_date_combined">\s*(Sold|Purchased):')


class HistoryParseError(ValueError):
    """Raised when the export doesn't match the expected Steam history shape."""


def load_history_json(path: str | Path) -> dict[str, Any]:
    """Load a raw `market/myhistory/render` JSON export from disk."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_transactions(payload: dict[str, Any]) -> list[Transaction]:
    """Extract transactions from a raw history payload's embedded HTML fragment.

    Steam's export doesn't provide structured per-transaction data directly;
    the `results_html` field is a server-rendered HTML table. This walks that
    fragment row by row rather than pulling in an HTML parsing dependency,
    since the row format is simple and stable enough for regex extraction.
    """
    results_html = payload.get("results_html", "")
    row_fragments = results_html.split(_ROW_SPLIT)[1:]

    return [_parse_row(fragment, index) for index, fragment in enumerate(row_fragments)]


def _parse_row(fragment: str, order_index: int) -> Transaction:
    price_match = _PRICE_RE.search(fragment)
    dates = _DATES_RE.findall(fragment)
    item_match = _ITEM_RE.search(fragment)
    game_match = _GAME_RE.search(fragment)
    action_match = _ACTION_RE.search(fragment)

    if not (price_match and len(dates) == 2 and item_match and game_match and action_match):
        raise HistoryParseError(f"could not parse history row at index {order_index}")

    amount, currency = parse_price(price_match.group(1))
    action = Action.SOLD if action_match.group(1) == "Sold" else Action.PURCHASED

    return Transaction(
        order_index=order_index,
        action=action,
        item_name=html.unescape(item_match.group(1)),
        game_name=html.unescape(game_match.group(1)),
        price=amount,
        currency=currency,
        acted_on=dates[0],
        listed_on=dates[1],
    )
