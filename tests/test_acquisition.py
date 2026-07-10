from decimal import Decimal

from steam_market_history.acquisition import (
    AMBIGUOUS,
    DROP,
    PURCHASED,
    ambiguous_best_guess,
    ambiguous_bounds,
    ambiguous_contributions,
    classify,
)
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


def test_classify_does_not_mix_the_same_item_name_across_currencies() -> None:
    # SMHT-9: purchased once in £, sold twice in € - the € sale has no
    # matching purchase *in its own currency*, so both € sales should be
    # confirmed drops. Before the fix, `classify` bucketed purely by
    # item_name, so the unrelated £ purchase would have "covered" one of
    # the € sales, mislabeling it PURCHASED and leaving only one AMBIGUOUS
    # instead of two DROPs.
    txns = [
        _txn(0, Action.PURCHASED, "1.00", item_name="Skin", currency="£"),
        _txn(1, Action.SOLD, "2.00", item_name="Skin", currency="€"),
        _txn(2, Action.SOLD, "3.00", item_name="Skin", currency="€"),
    ]

    result = classify(txns)

    eur_sales = [t for t in result if t.currency == "€"]
    assert all(s.acquisition == DROP for s in eur_sales)


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


def test_ambiguous_best_guess_uses_time_order_not_price() -> None:
    # 2 purchases, 3 sales - drop_count = 1. FIFO pairs the two *oldest*
    # sales (order_index 5 and 3, £1.00 and £100.00) to the two purchases
    # as real trades, leaving the single *newest* sale (order_index 1,
    # £2.00) as the guessed drop. That's independent of price ranking,
    # unlike ambiguous_bounds' min (£1.00 - matches the priciest sale to a
    # purchase) and max (£100.00 - matches the cheapest) - £2.00 sits
    # strictly between them, a genuinely different convention.
    txns = classify(
        [
            _txn(10, Action.PURCHASED, "1.00"),
            _txn(11, Action.PURCHASED, "1.00"),
            _txn(5, Action.SOLD, "1.00"),
            _txn(3, Action.SOLD, "100.00"),
            _txn(1, Action.SOLD, "2.00"),
        ]
    )

    bounds = ambiguous_bounds(txns)
    guess = ambiguous_best_guess(txns)

    assert bounds["£"].drop_revenue_min == Decimal("1.00")
    assert bounds["£"].drop_revenue_max == Decimal("100.00")
    assert guess["£"] == Decimal("2.00")


def test_ambiguous_best_guess_keeps_currencies_separate() -> None:
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

    guess = ambiguous_best_guess(txns)

    assert set(guess) == {"£", "€"}


def test_ambiguous_contributions_matches_the_worked_example() -> None:
    # Same fixture and reasoning as test_ambiguous_best_guess_uses_time_order_not_price:
    # order_index 3 (£100.00) is the sole max-bucket sale, order_index 1
    # (£2.00) is the sole best-guess sale, order_index 5 is in neither
    # bucket (matched to a purchase both ways).
    txns = classify(
        [
            _txn(10, Action.PURCHASED, "1.00"),
            _txn(11, Action.PURCHASED, "1.00"),
            _txn(5, Action.SOLD, "1.00"),
            _txn(3, Action.SOLD, "100.00"),
            _txn(1, Action.SOLD, "2.00"),
        ]
    )

    contributions = ambiguous_contributions(txns)

    assert contributions[5] == (Decimal("0"), Decimal("0"))
    assert contributions[3] == (Decimal("100.00"), Decimal("0"))
    assert contributions[1] == (Decimal("0"), Decimal("2.00"))
