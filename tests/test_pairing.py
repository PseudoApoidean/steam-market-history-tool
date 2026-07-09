from decimal import Decimal

from steam_market_history.models import Action, Transaction
from steam_market_history.pairing import fifo_pairs


def _txn(
    order_index: int,
    action: Action,
    price: str,
    item_name: str = "item",
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


def test_fifo_pairs_oldest_purchase_with_oldest_sale() -> None:
    # order_index 0 = most recent, so oldest is the highest order_index.
    txns = [
        _txn(3, Action.PURCHASED, "2.00"),  # oldest purchase
        _txn(1, Action.PURCHASED, "5.00"),  # newer purchase
        _txn(2, Action.SOLD, "3.00"),  # oldest sale
        _txn(0, Action.SOLD, "4.00"),  # newer sale
    ]

    pairs = fifo_pairs(txns)

    assert len(pairs) == 2
    assert pairs[0].purchase_price == Decimal("2.00")
    assert pairs[0].sale_price == Decimal("3.00")
    assert pairs[1].purchase_price == Decimal("5.00")
    assert pairs[1].sale_price == Decimal("4.00")


def test_fifo_pairs_excess_sales_are_unpaired() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "2.00"),
        _txn(1, Action.SOLD, "3.00"),  # newer sale - excess, a drop, not paired
        _txn(2, Action.SOLD, "5.00"),  # older sale - pairs with the one purchase
    ]

    pairs = fifo_pairs(txns)

    assert len(pairs) == 1
    assert pairs[0].sale_price == Decimal("5.00")


def test_fifo_pairs_excess_purchases_are_unpaired() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "2.00"),  # newer purchase - excess, still held, not paired
        _txn(1, Action.PURCHASED, "4.00"),  # older purchase - pairs with the one sale
        _txn(2, Action.SOLD, "3.00"),
    ]

    pairs = fifo_pairs(txns)

    assert len(pairs) == 1
    assert pairs[0].purchase_price == Decimal("4.00")


def test_fifo_pairs_keeps_item_names_independent() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "1.00", item_name="A"),
        _txn(1, Action.SOLD, "2.00", item_name="A"),
        _txn(2, Action.PURCHASED, "5.00", item_name="B"),
        _txn(3, Action.SOLD, "1.00", item_name="B"),
    ]

    pairs = fifo_pairs(txns)

    assert {p.item_name for p in pairs} == {"A", "B"}


def test_trade_pair_profit() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "5.00"),
        _txn(1, Action.SOLD, "3.00"),
    ]

    pairs = fifo_pairs(txns)

    assert pairs[0].profit == Decimal("-2.00")
