from decimal import Decimal

from steam_market_history.models import Action, Transaction
from steam_market_history.unrealized import compute_unrealized


def _txn(
    order_index: int,
    action: Action,
    price: str,
    item_name: str,
    currency: str = "£",
) -> Transaction:
    return Transaction(
        order_index=order_index,
        action=action,
        item_name=item_name,
        game_name="Rust",
        price=Decimal(price),
        currency=currency,
        acted_on="1 Jan",
        listed_on="1 Jan",
    )


def test_compute_unrealized_ignores_fully_sold_items() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "1.00", "Skin"),
        _txn(1, Action.SOLD, "2.00", "Skin"),
    ]

    items, missing = compute_unrealized(txns, {"Skin": Decimal("3.00")})

    assert items == {}
    assert missing == []


def test_compute_unrealized_single_held_purchase_has_no_bound_spread() -> None:
    txns = [_txn(0, Action.PURCHASED, "1.55", "Rat-a-tat-tat Thompson", currency="€")]

    items, missing = compute_unrealized(txns, {"Rat-a-tat-tat Thompson": Decimal("3.00")})

    item = items["Rat-a-tat-tat Thompson"]
    assert item.currency == "€"
    assert item.held_count == 1
    assert item.current_value == Decimal("3.00")
    assert item.gain_min == item.gain_max == Decimal("1.45")


def test_compute_unrealized_bounds_held_units_by_cheapest_or_priciest_purchase() -> None:
    # 3 purchased at 1.00/2.00/5.00, 1 sold -> 2 still held. Which specific
    # 2 remain can't be known, so gain_max assumes the cheapest 2 remain
    # (lowest cost basis, 1.00+2.00=3.00) and gain_min assumes the priciest
    # 2 remain (highest cost basis, 2.00+5.00=7.00).
    txns = [
        _txn(0, Action.PURCHASED, "1.00", "Skin"),
        _txn(1, Action.PURCHASED, "2.00", "Skin"),
        _txn(2, Action.PURCHASED, "5.00", "Skin"),
        _txn(3, Action.SOLD, "9.00", "Skin"),
    ]

    items, missing = compute_unrealized(txns, {"Skin": Decimal("10.00")})

    item = items["Skin"]
    assert item.held_count == 2
    assert item.current_value == Decimal("20.00")
    assert item.gain_max == Decimal("20.00") - Decimal("3.00")
    assert item.gain_min == Decimal("20.00") - Decimal("7.00")


def test_compute_unrealized_reports_missing_prices_without_dropping_silently() -> None:
    txns = [_txn(0, Action.PURCHASED, "1.00", "Skin")]

    items, missing = compute_unrealized(txns, {})

    assert items == {}
    assert missing == ["Skin"]


def test_compute_unrealized_keeps_currencies_and_items_separate() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "1.00", "Skin A", currency="£"),
        _txn(1, Action.PURCHASED, "2.00", "Skin B", currency="€"),
    ]

    items, missing = compute_unrealized(
        txns, {"Skin A": Decimal("2.00"), "Skin B": Decimal("3.00")}
    )

    assert items["Skin A"].currency == "£"
    assert items["Skin B"].currency == "€"
    assert missing == []
