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
_ROW_ID_RE = re.compile(r'id="(history_row_\d+_\d+)"')
_HOVER_RE = re.compile(
    r"CreateItemHoverFromContainer\(\s*g_rgAssets,\s*'(history_row_\d+_\d+)_name',"
    r"\s*(\d+),\s*'(\d+)',\s*'(\d+)'"
)

# Every card/emoticon/profile-background/booster-pack files under this one
# generic appid ("Steam"), regardless of which game it's themed after -
# confirmed against a real export. Real economy items keep their own game's
# appid and already report a clean `market_listing_game_name`, so this is
# the only special case needed.
_STEAM_COMMUNITY_APPID = "753"


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

    `assets`/`hovers`, when present, let a row's `game_name` be corrected
    (community items - cards, emoticons, etc. - report a conflated string
    otherwise, see `_STEAM_COMMUNITY_APPID`) and a `category` populated. A
    row with no corresponding `hovers` entry falls back to the HTML-only
    behavior rather than failing - this linkage isn't guaranteed present for
    every export.
    """
    results_html = payload.get("results_html", "")
    row_fragments = results_html.split(_ROW_SPLIT)[1:]
    hover_map = _parse_hovers(payload.get("hovers", ""))
    assets = payload.get("assets", {})

    return [
        _parse_row(fragment, index, hover_map, assets)
        for index, fragment in enumerate(row_fragments)
    ]


def _parse_hovers(hovers: str) -> dict[str, tuple[str, str, str]]:
    """Map a row id to its `(appid, contextid, assetid)` triple.

    `hovers` is a blob of `CreateItemHoverFromContainer(g_rgAssets, id, ...)`
    JS calls, one per row (matching a `_name`/`_image` HTML element id) - the
    only link between `results_html`'s rows and the `assets` map.
    """
    return {
        match.group(1): (match.group(2), match.group(3), match.group(4))
        for match in _HOVER_RE.finditer(hovers)
    }


def _parse_row(
    fragment: str,
    order_index: int,
    hover_map: dict[str, tuple[str, str, str]],
    assets: dict[str, Any],
) -> Transaction:
    price_match = _PRICE_RE.search(fragment)
    dates = _DATES_RE.findall(fragment)
    item_match = _ITEM_RE.search(fragment)
    game_match = _GAME_RE.search(fragment)
    action_match = _ACTION_RE.search(fragment)

    if not (price_match and len(dates) == 2 and item_match and game_match and action_match):
        raise HistoryParseError(f"could not parse history row at index {order_index}")

    amount, currency = parse_price(price_match.group(1))
    action = Action.SOLD if action_match.group(1) == "Sold" else Action.PURCHASED
    game_name = html.unescape(game_match.group(1))
    category = None

    row_id_match = _ROW_ID_RE.search(fragment)
    hover = hover_map.get(row_id_match.group(1)) if row_id_match else None
    if hover:
        appid, contextid, assetid = hover
        asset = assets.get(appid, {}).get(contextid, {}).get(assetid)
        if asset:
            if appid == _STEAM_COMMUNITY_APPID:
                game_name = "Steam"
            category = asset.get("type") or None

    return Transaction(
        order_index=order_index,
        action=action,
        item_name=html.unescape(item_match.group(1)),
        game_name=game_name,
        price=amount,
        currency=currency,
        acted_on=dates[0],
        listed_on=dates[1],
        category=category,
    )
