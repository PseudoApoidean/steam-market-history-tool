from decimal import Decimal

from steam_market_history.acquisition import AMBIGUOUS, DROP, PURCHASED, ambiguous_bounds, classify
from steam_market_history.models import Action, Transaction


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


def test_classify_confirmed_drop_when_never_purchased() -> None:
    txns = [_txn(0, Action.SOLD, "1.00")]

    result = classify(txns)

    assert result[0].acquisition == DROP


def test_classify_ambiguous_when_sold_more_than_purchased() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "1.00"),
        _txn(1, Action.SOLD, "2.00"),
        _txn(2, Action.SOLD, "3.00"),
    ]

    result = classify(txns)

    purchase = next(t for t in result if t.action is Action.PURCHASED)
    sales = [t for t in result if t.action is Action.SOLD]
    assert purchase.acquisition == PURCHASED
    assert all(s.acquisition == AMBIGUOUS for s in sales)


def test_classify_purchased_default_when_not_forced() -> None:
    txns = [
        _txn(0, Action.PURCHASED, "1.00"),
        _txn(1, Action.PURCHASED, "1.50"),
        _txn(2, Action.SOLD, "2.00"),
    ]

    result = classify(txns)

    sale = next(t for t in result if t.action is Action.SOLD)
    assert sale.acquisition == PURCHASED


def test_classify_purchase_rows_are_always_purchased() -> None:
    # Even for an item sold far more than purchased, the purchase rows
    # themselves are never anything but "purchased".
    txns = [
        _txn(0, Action.PURCHASED, "1.00"),
        _txn(1, Action.SOLD, "2.00"),
        _txn(2, Action.SOLD, "3.00"),
        _txn(3, Action.SOLD, "4.00"),
    ]

    result = classify(txns)

    purchase = next(t for t in result if t.action is Action.PURCHASED)
    assert purchase.acquisition == PURCHASED


def test_classify_keeps_item_names_independent() -> None:
    # A confirmed-drop item shouldn't affect an unrelated item's
    # classification, even in the same transaction list.
    txns = [
        _txn(0, Action.SOLD, "1.00", item_name="Drop Item"),
        _txn(1, Action.PURCHASED, "1.00", item_name="Traded Item"),
        _txn(2, Action.SOLD, "2.00", item_name="Traded Item"),
    ]

    result = classify(txns)

    drop = next(t for t in result if t.item_name == "Drop Item")
    traded = next(t for t in result if t.item_name == "Traded Item" and t.action is Action.SOLD)
    assert drop.acquisition == DROP
    assert traded.acquisition == PURCHASED


def test_ambiguous_bounds_worked_example() -> None:
    # Two purchases, five sales of the same item, price trending up - the
    # example from the "Confirmed vs Ambiguous Item Acquisition" design
    # doc. Matched-to-highest-sales minimizes drop revenue (£17); matched-
    # to-lowest-sales maximizes it (£37).
    txns = classify(
        [
            _txn(0, Action.PURCHASED, "2.00"),
            _txn(1, Action.PURCHASED, "5.00"),
            _txn(2, Action.SOLD, "3.00"),
            _txn(3, Action.SOLD, "4.00"),
            _txn(4, Action.SOLD, "10.00"),
            _txn(5, Action.SOLD, "12.00"),
            _txn(6, Action.SOLD, "15.00"),
        ]
    )

    bounds = ambiguous_bounds(txns)

    assert bounds["£"].drop_revenue_min == Decimal("17.00")
    assert bounds["£"].drop_revenue_max == Decimal("37.00")


def test_ambiguous_bounds_keeps_currencies_separate() -> None:
    txns = classify(
        [
            _txn(0, Action.PURCHASED, "1.00", item_name="GBP Item", currency="£"),
            _txn(1, Action.SOLD, "2.00", item_name="GBP Item", currency="£"),
            _txn(2, Action.SOLD, "3.00", item_name="GBP Item", currency="£"),
            _txn(3, Action.PURCHASED, "1.00", item_name="EUR Item", currency="€"),
            _txn(4, Action.SOLD, "5.00", item_name="EUR Item", currency="€"),
            _txn(5, Action.SOLD, "6.00", item_name="EUR Item", currency="€"),
        ]
    )

    bounds = ambiguous_bounds(txns)

    assert set(bounds) == {"£", "€"}
    assert bounds["£"].drop_revenue_min == Decimal("2.00")
    assert bounds["€"].drop_revenue_min == Decimal("5.00")


def test_ambiguous_bounds_empty_when_nothing_ambiguous() -> None:
    txns = classify(
        [
            _txn(0, Action.PURCHASED, "1.00"),
            _txn(1, Action.SOLD, "2.00"),
        ]
    )

    assert ambiguous_bounds(txns) == {}
