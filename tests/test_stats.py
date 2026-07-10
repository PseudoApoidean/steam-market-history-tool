from decimal import Decimal

from steam_market_history.acquisition import classify
from steam_market_history.models import Action, Transaction
from steam_market_history.pairing import fifo_pairs
from steam_market_history.stats import (
    cumulative_series,
    summarize,
    summarize_acquisition,
    summarize_by_category,
    summarize_by_game,
    summarize_by_item,
    summarize_unrealized,
    summarize_win_rate,
)
from steam_market_history.unrealized import UnrealizedItem


def _txn(
    order_index: int,
    game_name: str,
    action: Action,
    price: str,
    currency: str = "£",
    item_name: str | None = None,
    category: str | None = None,
    appid: str | None = None,
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
        category=category,
        appid=appid,
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


def test_summarize_by_game_captures_appid() -> None:
    txns = [
        _txn(0, "Steam", Action.SOLD, "1.00", appid="753"),
        _txn(1, "Rust", Action.PURCHASED, "1.00", appid=None),
    ]

    by_game = summarize_by_game(txns)

    assert by_game["Steam"].appid == "753"
    assert by_game["Rust"].appid is None


def test_summarize_by_category_scopes_categories_per_game() -> None:
    """A category isn't exclusive to one game_name - two different games can
    each have their own same-named category, and totals must stay scoped
    to the game they actually belong to rather than getting mixed."""
    txns = [
        _txn(0, "Steam", Action.SOLD, "2.00", category="Trading Card"),
        _txn(1, "Counter-Strike 2", Action.SOLD, "5.00", category="Container"),
        _txn(2, "Counter-Strike 2", Action.PURCHASED, "3.00", category="Container"),
        _txn(3, "Rust", Action.SOLD, "1.00", category=None),
    ]

    by_category = summarize_by_category(txns)

    assert by_category["Steam"]["Trading Card"].totals_by_currency["£"].net_profit == Decimal(
        "2.00"
    )
    assert by_category["Counter-Strike 2"]["Container"].totals_by_currency[
        "£"
    ].net_profit == Decimal("2.00")
    # Rust's only transaction has no category - excluded entirely, not an
    # empty per-game entry.
    assert "Rust" not in by_category


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


def test_summarize_win_rate_counts_profitable_losing_and_breakeven() -> None:
    txns = [
        _txn(0, "Rust", Action.PURCHASED, "1.00", item_name="Win"),
        _txn(1, "Rust", Action.SOLD, "2.00", item_name="Win"),
        _txn(2, "Rust", Action.PURCHASED, "5.00", item_name="Loss"),
        _txn(3, "Rust", Action.SOLD, "3.00", item_name="Loss"),
        _txn(4, "Rust", Action.PURCHASED, "4.00", item_name="Even"),
        _txn(5, "Rust", Action.SOLD, "4.00", item_name="Even"),
    ]

    win_rate = summarize_win_rate(fifo_pairs(txns))

    assert win_rate["£"].profitable_count == 1
    assert win_rate["£"].losing_count == 1
    assert win_rate["£"].breakeven_count == 1


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


def test_cumulative_series_points_carry_the_item_that_produced_them() -> None:
    txns = [
        _txn(0, "Rust", Action.SOLD, "1.00", item_name="Door Skin"),
        _txn(1, "Rust", Action.PURCHASED, "0.50", item_name="Metal Facemask"),
    ]

    series = cumulative_series(txns)

    points = series["£"]
    # Oldest first, so order_index 1 (Metal Facemask) comes before 0 (Door Skin).
    assert [p.item_name for p in points] == ["Metal Facemask", "Door Skin"]


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


def test_summarize_unrealized_aggregates_by_currency() -> None:
    items = {
        "Skin A": UnrealizedItem(
            item_name="Skin A",
            currency="£",
            held_count=1,
            current_value=Decimal("5.00"),
            gain_min=Decimal("2.00"),
            gain_max=Decimal("3.00"),
        ),
        "Skin B": UnrealizedItem(
            item_name="Skin B",
            currency="£",
            held_count=2,
            current_value=Decimal("4.00"),
            gain_min=Decimal("-1.00"),
            gain_max=Decimal("1.00"),
        ),
        "Skin C": UnrealizedItem(
            item_name="Skin C",
            currency="€",
            held_count=1,
            current_value=Decimal("3.00"),
            gain_min=Decimal("1.00"),
            gain_max=Decimal("1.00"),
        ),
    }

    summary = summarize_unrealized(items)

    assert summary["£"].held_count == 3
    assert summary["£"].current_value == Decimal("9.00")
    assert summary["£"].gain_min == Decimal("1.00")
    assert summary["£"].gain_max == Decimal("4.00")
    assert summary["€"].held_count == 1
    assert summary["€"].current_value == Decimal("3.00")
