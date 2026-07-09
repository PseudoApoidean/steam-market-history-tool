from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Action, Transaction


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


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    order_index: int
    acted_on: str
    cumulative_net_profit: Decimal


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
        bucket = game.totals_by_currency.setdefault(
            txn.currency, CurrencyTotals(currency=txn.currency)
        )
        _apply(bucket, txn)
    return by_game


def cumulative_series(transactions: Iterable[Transaction]) -> dict[str, list[SeriesPoint]]:
    """Running net-profit total per currency, oldest transaction first.

    Steam's export has no year in `acted_on`/`listed_on`, so `order_index`
    (0 = most recent) is the only reliable ordering signal across the whole
    history - see `Transaction`'s docstring. Sorting by `order_index`
    descending therefore gives oldest-first order without relying on the
    date strings at all. Currencies are kept separate for the same reason
    `summarize` keeps them separate: mixing requires an exchange rate this
    data doesn't have.
    """
    series: dict[str, list[SeriesPoint]] = {}
    running: dict[str, Decimal] = {}
    for txn in sorted(transactions, key=lambda t: t.order_index, reverse=True):
        delta = txn.price if txn.action is Action.SOLD else -txn.price
        total = running.get(txn.currency, Decimal("0")) + delta
        running[txn.currency] = total
        series.setdefault(txn.currency, []).append(
            SeriesPoint(order_index=txn.order_index, acted_on=txn.acted_on, cumulative_net_profit=total)
        )
    return series


def _apply(bucket: CurrencyTotals, txn: Transaction) -> None:
    if txn.action is Action.SOLD:
        bucket.sold_total += txn.price
        bucket.sold_count += 1
    else:
        bucket.purchased_total += txn.price
        bucket.purchased_count += 1
