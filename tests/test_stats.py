from decimal import Decimal

from steam_market_history.acquisition import classify
from steam_market_history.models import Action, Transaction
from steam_market_history.stats import (
    cumulative_series,
    summarize,
    summarize_acquisition,
    summarize_by_game,
    summarize_by_item,
)


def _txn(
    order_index: int,
    game_name: str,
    action: Action,
    price: str,
    currency: str = "£",
    item_name: str | None = None,
) -> Transaction:
    return Transaction(
        order_index=order_index,
        action=action,
        item_name=item_name if item_name is not None else f"item-{order_index}",
        game_name=game_name,
        price=Decimal(price),
        currency=currency,
        acted_on="1 Jan",
        listed_on="1 Jan",
    )


def test_summarize_computes_net_profit_per_currency() -> None:
    txns = [
        _txn(0, "Rust", Action.SOLD, "2.00", currency="£"),
        _txn(1, "Rust", Action.PURCHASED, "0.50", currency="£"),
        _txn(2, "Rust", Action.SOLD, "1.00", currency="€"),
    ]

    totals = summarize(txns)

    assert totals["£"].sold_total == Decimal("2.00")
    assert totals["£"].sold_count == 1
    assert totals["£"].purchased_total == Decimal("0.50")
    assert totals["£"].purchased_count == 1
    assert totals["£"].net_profit == Decimal("1.50")

    assert totals["€"].sold_total == Decimal("1.00")
    assert totals["€"].purchased_total == Decimal("0")
    assert totals["€"].net_profit == Decimal("1.00")


def test_summarize_by_game_keeps_games_separate() -> None:
    txns = [
        _txn(0, "Rust", Action.SOLD, "2.00"),
        _txn(1, "Counter-Strike 2", Action.PURCHASED, "3.00"),
    ]

    by_game = summarize_by_game(txns)

    assert by_game["Rust"].totals_by_currency["£"].net_profit == Decimal("2.00")
    assert by_game["Counter-Strike 2"].totals_by_currency["£"].net_profit == Decimal("-3.00")


def test_summarize_by_item_keeps_items_separate() -> None:
    txns = [
        _txn(0, "Rust", Action.SOLD, "5.00", item_name="Skin A"),
        _txn(1, "Rust", Action.PURCHASED, "2.00", item_name="Skin A"),
        _txn(2, "Rust", Action.SOLD, "1.00", item_name="Skin B"),
    ]

    by_item = summarize_by_item(txns)

    assert by_item["Skin A"].totals_by_currency["£"].net_profit == Decimal("3.00")
    assert by_item["Skin B"].totals_by_currency["£"].net_profit == Decimal("1.00")
    # Different grouping key than by_game - items from the same game don't
    # collapse together the way they would in summarize_by_game.
    assert set(by_item) == {"Skin A", "Skin B"}


def test_cumulative_series_is_oldest_first_and_running() -> None:
    # order_index 0 = most recent, per Transaction's own contract, so
    # oldest-first means highest order_index first.
    txns = [
        _txn(0, "Rust", Action.SOLD, "1.00", currency="£"),
        _txn(1, "Rust", Action.PURCHASED, "0.50", currency="£"),
        _txn(2, "Rust", Action.SOLD, "2.00", currency="£"),
    ]

    series = cumulative_series(txns)

    points = series["£"]
    assert [p.order_index for p in points] == [2, 1, 0]
    assert [p.cumulative_net_profit for p in points] == [
        Decimal("2.00"),
        Decimal("1.50"),
        Decimal("2.50"),
    ]


def test_cumulative_series_keeps_currencies_separate() -> None:
    txns = [
        _txn(0, "Rust", Action.SOLD, "1.00", currency="£"),
        _txn(1, "Rust", Action.SOLD, "3.00", currency="€"),
    ]

    series = cumulative_series(txns)

    assert [p.cumulative_net_profit for p in series["£"]] == [Decimal("1.00")]
    assert [p.cumulative_net_profit for p in series["€"]] == [Decimal("3.00")]


def test_summarize_acquisition_confirmed_drop_is_exact() -> None:
    txns = classify(
        [
            _txn(0, "Rust", Action.SOLD, "5.00", item_name="Never Bought"),
        ]
    )

    summary = summarize_acquisition(txns)

    assert summary["£"].confirmed_drop_revenue == Decimal("5.00")
    assert summary["£"].confirmed_drop_count == 1
    assert summary["£"].ambiguous_count == 0


def test_summarize_acquisition_ambiguous_bucket_is_a_range() -> None:
    txns = classify(
        [
            _txn(0, "Rust", Action.PURCHASED, "1.00", item_name="Skin"),
            _txn(1, "Rust", Action.SOLD, "2.00", item_name="Skin"),
            _txn(2, "Rust", Action.SOLD, "4.00", item_name="Skin"),
        ]
    )

    summary = summarize_acquisition(txns)

    assert summary["£"].ambiguous_count == 2
    assert summary["£"].confirmed_drop_count == 0
    # matched=highest (4.00) -> min drop revenue = 2.00; matched=lowest
    # (2.00) -> max drop revenue = 4.00.
    assert summary["£"].ambiguous_drop_revenue_min == Decimal("2.00")
    assert summary["£"].ambiguous_drop_revenue_max == Decimal("4.00")
