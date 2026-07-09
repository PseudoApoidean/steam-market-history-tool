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

    second = transactions[1]
    assert second.action is Action.PURCHASED
    assert second.game_name == "Rust"
    assert second.price == Decimal("1.55")
    assert second.currency == "£"
    # No hovers entry for this row in the fixture - falls back cleanly.
    assert second.category is None

    third = transactions[2]
    assert third.action is Action.SOLD
    assert third.item_name == "Fire & Ice Case"  # HTML entity decoded
    assert third.price == Decimal("2.00")
    assert third.currency == "€"
    # appid 753 - game_name corrected to "Steam" regardless of the raw
    # HTML string ("Team Fortress 2"), category from the asset's `type`.
    assert third.game_name == "Steam"
    assert third.category == "Fire & Ice Case Trading Card"
