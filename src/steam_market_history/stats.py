from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from . import acquisition
from .models import Action, Transaction
from .pairing import TradePair
from .unrealized import UnrealizedItem


@dataclass
class CurrencyTotals:
    currency: str
    sold_total: Decimal = Decimal("0")
    sold_count: int = 0
    purchased_total: Decimal = Decimal("0")
    purchased_count: int = 0

    @property
    def net_profit(self) -> Decimal:
        return self.sold_total - self.purchased_total


@dataclass
class GameSummary:
    game_name: str
    totals_by_currency: dict[str, CurrencyTotals] = field(default_factory=dict)
    # First non-None appid seen for this game_name - should be consistent
    # across every transaction under one game_name by construction (see
    # parser.py's _STEAM_COMMUNITY_APPID correction), so "first" and "only"
    # are expected to coincide in practice.
    appid: str | None = None


@dataclass
class ItemSummary:
    item_name: str
    totals_by_currency: dict[str, CurrencyTotals] = field(default_factory=dict)


@dataclass
class CategorySummary:
    category: str
    totals_by_currency: dict[str, CurrencyTotals] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    order_index: int
    acted_on: str
    item_name: str
    cumulative_net_profit: Decimal


@dataclass
class WinRateSummary:
    currency: str
    profitable_count: int = 0
    losing_count: int = 0
    breakeven_count: int = 0


@dataclass
class AcquisitionSummary:
    currency: str
    confirmed_drop_revenue: Decimal = Decimal("0")
    confirmed_drop_count: int = 0
    ambiguous_count: int = 0
    ambiguous_drop_revenue_min: Decimal = Decimal("0")
    ambiguous_drop_revenue_max: Decimal = Decimal("0")


@dataclass
class UnrealizedSummary:
    currency: str
    held_count: int = 0
    current_value: Decimal = Decimal("0")
    gain_min: Decimal = Decimal("0")
    gain_max: Decimal = Decimal("0")


def summarize(transactions: Iterable[Transaction]) -> dict[str, CurrencyTotals]:
    """Lifetime profit/loss per currency across all given transactions.

    Currencies are never mixed together: converting requires an exchange
    rate and a point in time, neither of which this data provides.
    """
    totals: dict[str, CurrencyTotals] = {}
    for txn in transactions:
        bucket = totals.setdefault(txn.currency, CurrencyTotals(currency=txn.currency))
        _apply(bucket, txn)
    return totals


def summarize_by_game(transactions: Iterable[Transaction]) -> dict[str, GameSummary]:
    """Per-game profit/loss, each broken down by currency."""
    by_game: dict[str, GameSummary] = {}
    for txn in transactions:
        game = by_game.setdefault(txn.game_name, GameSummary(game_name=txn.game_name))
        if game.appid is None and txn.appid is not None:
            game.appid = txn.appid
        bucket = game.totals_by_currency.setdefault(
            txn.currency, CurrencyTotals(currency=txn.currency)
        )
        _apply(bucket, txn)
    return by_game


def summarize_by_category(transactions: Iterable[Transaction]) -> dict[str, dict[str, CategorySummary]]:
    """Per-game, per-category profit/loss, each broken down by currency.

    Keyed by `(game_name, category)` rather than `category` alone -
    `category` isn't exclusive to any one `game_name` (the `753`/"Steam"
    correction only affects *which* `game_name` an item's category-carrying
    `type` value ends up filed under; a real game like "Counter-Strike 2"
    can have its own meaningful categories too, e.g. containers vs. skins).
    Nesting under `game_name` keeps every category total scoped to the game
    it actually belongs to, rather than mixing categories across unrelated
    games under one flat bucket. Transactions with no `category` (no
    resolvable `hovers`/`assets` match - see `parser.py`) are excluded
    entirely, same as they're absent from `by_game`'s totals for any field
    that depends on that linkage.
    """
    by_game_category: dict[str, dict[str, CategorySummary]] = {}
    for txn in transactions:
        if txn.category is None:
            continue
        categories = by_game_category.setdefault(txn.game_name, {})
        summary = categories.setdefault(txn.category, CategorySummary(category=txn.category))
        bucket = summary.totals_by_currency.setdefault(
            txn.currency, CurrencyTotals(currency=txn.currency)
        )
        _apply(bucket, txn)
    return by_game_category


def summarize_by_item(transactions: Iterable[Transaction]) -> dict[str, ItemSummary]:
    """Per-item-name profit/loss, each broken down by currency.

    Same shape and caveats as `summarize_by_game`, just grouped by
    `item_name` instead. Ranking (most/least profitable) is left to the
    caller - sort this dict's values by whichever currency/field matters,
    same as callers already do for `by_game`. No caller-side filtering is
    applied here: a drop item's full sale price counts as profit with no
    cost basis, same as it does in the lifetime totals - filter by
    `acquisition:purchased` first (see `filters.py`) if a "real trades
    only" ranking is wanted instead.
    """
    by_item: dict[str, ItemSummary] = {}
    for txn in transactions:
        item = by_item.setdefault(txn.item_name, ItemSummary(item_name=txn.item_name))
        bucket = item.totals_by_currency.setdefault(
            txn.currency, CurrencyTotals(currency=txn.currency)
        )
        _apply(bucket, txn)
    return by_item


def cumulative_series(transactions: Iterable[Transaction]) -> dict[str, list[SeriesPoint]]:
    """Running net-profit total per currency, oldest transaction first.

    Steam's export has no year in `acted_on`/`listed_on`, so `order_index`
    (0 = most recent) is the only reliable ordering signal across the whole
    history - see `Transaction`'s docstring. Sorting by `order_index`
    descending therefore gives oldest-first order without relying on the
    date strings at all. Currencies are kept separate for the same reason
    `summarize` keeps them separate: mixing requires an exchange rate this
    data doesn't have.

    Each point's `item_name` is the transaction that produced it - the
    item whose sale/purchase pushed the running total to that value - so a
    caller can answer "what caused this swing" without a separate lookup
    against the raw transaction list, which this tool's `--json` output
    never exposes.
    """
    series: dict[str, list[SeriesPoint]] = {}
    running: dict[str, Decimal] = {}
    for txn in sorted(transactions, key=lambda t: t.order_index, reverse=True):
        delta = txn.price if txn.action is Action.SOLD else -txn.price
        total = running.get(txn.currency, Decimal("0")) + delta
        running[txn.currency] = total
        series.setdefault(txn.currency, []).append(
            SeriesPoint(
                order_index=txn.order_index,
                acted_on=txn.acted_on,
                item_name=txn.item_name,
                cumulative_net_profit=total,
            )
        )
    return series


def summarize_win_rate(pairs: Iterable[TradePair]) -> dict[str, WinRateSummary]:
    """Per currency, how many FIFO-paired trades were profitable/losing/breakeven.

    Takes `pairing.fifo_pairs`' output, not raw transactions - this is a
    simple win/loss/breakeven count, not a full profit distribution (a
    histogram or similar could be a later enhancement if wanted).
    """
    summaries: dict[str, WinRateSummary] = {}
    for pair in pairs:
        bucket = summaries.setdefault(pair.currency, WinRateSummary(currency=pair.currency))
        if pair.profit > 0:
            bucket.profitable_count += 1
        elif pair.profit < 0:
            bucket.losing_count += 1
        else:
            bucket.breakeven_count += 1
    return summaries


def summarize_acquisition(transactions: Iterable[Transaction]) -> dict[str, AcquisitionSummary]:
    """Per currency, confirmed drop revenue and the ambiguous-bucket bounds.

    Requires transactions to have already been through `acquisition.classify`.
    `confirmed_drop_revenue`/`confirmed_drop_count` are exact - a hard floor,
    never adjusted later. `ambiguous_drop_revenue_min`/`_max` bound what's
    consistent with the data for sales that can't be individually resolved -
    see `acquisition.ambiguous_bounds` and the "Confirmed vs Ambiguous Item
    Acquisition" design doc for why this is a range, not a single guess.
    """
    transactions = list(transactions)
    summaries: dict[str, AcquisitionSummary] = {}

    for txn in transactions:
        if txn.acquisition == acquisition.DROP:
            bucket = summaries.setdefault(
                txn.currency, AcquisitionSummary(currency=txn.currency)
            )
            bucket.confirmed_drop_revenue += txn.price
            bucket.confirmed_drop_count += 1
        elif txn.acquisition == acquisition.AMBIGUOUS:
            bucket = summaries.setdefault(
                txn.currency, AcquisitionSummary(currency=txn.currency)
            )
            bucket.ambiguous_count += 1

    for currency, bounds in acquisition.ambiguous_bounds(transactions).items():
        bucket = summaries.setdefault(currency, AcquisitionSummary(currency=currency))
        bucket.ambiguous_drop_revenue_min = bounds.drop_revenue_min
        bucket.ambiguous_drop_revenue_max = bounds.drop_revenue_max

    return summaries


def summarize_unrealized(
    items: dict[tuple[str, str], UnrealizedItem],
) -> dict[str, UnrealizedSummary]:
    """Per currency, aggregate `unrealized.compute_unrealized`'s per-item bounds."""
    summaries: dict[str, UnrealizedSummary] = {}
    for item in items.values():
        bucket = summaries.setdefault(item.currency, UnrealizedSummary(currency=item.currency))
        bucket.held_count += item.held_count
        bucket.current_value += item.current_value
        bucket.gain_min += item.gain_min
        bucket.gain_max += item.gain_max
    return summaries


def _apply(bucket: CurrencyTotals, txn: Transaction) -> None:
    if txn.action is Action.SOLD:
        bucket.sold_total += txn.price
        bucket.sold_count += 1
    else:
        bucket.purchased_total += txn.price
        bucket.purchased_count += 1
