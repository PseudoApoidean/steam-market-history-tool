from decimal import Decimal
from pathlib import Path

from steam_market_history.models import Action
from steam_market_history.parser import load_history_json, parse_transactions

FIXTURE = Path(__file__).parent / "fixtures" / "sample_history.json"


def test_parse_transactions_from_fixture() -> None:
    payload = load_history_json(FIXTURE)
    transactions = parse_transactions(payload)

    assert len(transactions) == 3

    first = transactions[0]
    assert first.order_index == 0
    assert first.action is Action.SOLD
    assert first.item_name == "Kilowatt Case"
    assert first.game_name == "Counter-Strike 2"
    assert first.price == Decimal("0.17")
    assert first.currency == "£"
    assert first.acted_on == "19 Jun"
    assert first.listed_on == "19 Jun"
    # appid 730 (non-753) - game_name passes through unchanged, category
    # comes from the assets/hovers linkage.
    assert first.category == "Base Grade Container"
    assert first.appid == "730"

    second = transactions[1]
    assert second.action is Action.PURCHASED
    assert second.game_name == "Rust"
    assert second.price == Decimal("1.55")
    assert second.currency == "£"
    # No hovers entry for this row in the fixture - falls back cleanly.
    assert second.category is None
    assert second.appid is None

    third = transactions[2]
    assert third.action is Action.SOLD
    assert third.item_name == "Fire & Ice Case"  # HTML entity decoded
    assert third.price == Decimal("2.00")
    assert third.currency == "€"
    # appid 753 - game_name corrected to "Steam" regardless of the raw
    # HTML string ("Team Fortress 2"), category from the asset's `type`.
    assert third.game_name == "Steam"
    assert third.category == "Fire & Ice Case Trading Card"
    assert third.appid == "753"


def test_appid_captured_even_when_assets_lookup_fails() -> None:
    """appid only needs the `hovers` blob; `category` additionally needs a
    matching `assets` entry - a hover pointing at an appid/contextid/assetid
    triple missing from `assets` should still yield an `appid`, just no
    `category`."""
    row_html = (
        '<div class="market_listing_row market_recent_listing_row" id="history_row_9_9">'
        '<div class="market_listing_right_cell market_listing_their_price">'
        '<span class="market_listing_price">£1.00</span></div>'
        '<div class="market_listing_right_cell market_listing_listed_date can_combine">1 Jan</div>'
        '<div class="market_listing_right_cell market_listing_listed_date can_combine">1 Jan</div>'
        '<span id="history_row_9_9_name" class="market_listing_item_name">Widget</span>'
        '<span class="market_listing_game_name">Widgetville</span>'
        '<div class="market_listing_listed_date_combined">Sold: 1 Jan</div>'
        "</div>"
    )
    payload = {
        "assets": {},
        "hovers": (
            "CreateItemHoverFromContainer( g_rgAssets, 'history_row_9_9_name', "
            "999, '1', '1', 0 );"
        ),
        "results_html": "market_listing_table_header" + row_html,
    }

    transactions = parse_transactions(payload)

    assert len(transactions) == 1
    assert transactions[0].appid == "999"
    assert transactions[0].category is None
