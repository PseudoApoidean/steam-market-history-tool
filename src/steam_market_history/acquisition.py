from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from .models import Action, Transaction

DROP = "drop"
AMBIGUOUS = "ambiguous"
PURCHASED = "purchased"


def classify(transactions: Sequence[Transaction]) -> list[Transaction]:
    """Label each transaction's `acquisition`, per (item name, currency).

    Per (item name, currency) - SMHT-9: bucketed by currency as well as
    item name, not item name alone, so a purchase/sale reconciliation
    never silently mixes two different currencies' amounts together as
    if they were one fungible pool - with `purchased` = purchase count
    and `sold` = sale count:

    - `purchased == 0`: every sale is a confirmed `DROP` - there's no
      purchase it could possibly correspond to, a fact of the data, not a
      guess.
    - `0 < purchased < sold`: every sale is `AMBIGUOUS` - exactly
      `sold - purchased` of them must be drops (pigeonhole), but not any
      specific one; see `ambiguous_bounds` for the aggregate consequence of
      that. Deliberately not resolved with a single-guess pairing (e.g.
      FIFO) - a specific pairing convention would change the actual £ split
      between trade profit and drop revenue, not just relabel it, so
      presenting one as fact would misrepresent the data. See the
      "Confirmed vs Ambiguous Item Acquisition" design doc for the full
      reasoning and a worked example.
    - `sold <= purchased`: stays `PURCHASED` (the default) - nothing forces
      a drop.

    Purchase rows are always `PURCHASED`.
    """
    counts: dict[tuple[str, str], tuple[int, int]] = {}
    for txn in transactions:
        key = (txn.item_name, txn.currency)
        purchased, sold = counts.get(key, (0, 0))
        if txn.action is Action.PURCHASED:
            counts[key] = (purchased + 1, sold)
        else:
            counts[key] = (purchased, sold + 1)

    result = []
    for txn in transactions:
        if txn.action is Action.PURCHASED:
            result.append(txn)
            continue
        purchased, sold = counts[(txn.item_name, txn.currency)]
        if purchased == 0:
            result.append(replace(txn, acquisition=DROP))
        elif sold > purchased:
            result.append(replace(txn, acquisition=AMBIGUOUS))
        else:
            result.append(txn)
    return result


@dataclass(frozen=True, slots=True)
class AmbiguousBounds:
    currency: str
    drop_revenue_min: Decimal
    drop_revenue_max: Decimal


def _ambiguous_groups(
    transactions: Iterable[Transaction],
) -> dict[tuple[str, str], tuple[list[Transaction], int]]:
    """Per (item name, currency), that group's ambiguous sales and purchase count.

    Shared grouping step behind `ambiguous_bounds`, `ambiguous_best_guess`,
    and `ambiguous_contributions` below - all three need exactly this same
    per-item bucketing (SMHT-9: by currency as well as item name, so a
    currency-mixed item name's purchases/sales are never reconciled
    against each other as one pool), just resolved into a different
    single number (or per-transaction breakdown) afterward.

    Requires `classify` to have already been run - reads `.acquisition`.
    """
    ambiguous_sales: dict[tuple[str, str], list[Transaction]] = {}
    purchased_counts: dict[tuple[str, str], int] = {}
    for txn in transactions:
        key = (txn.item_name, txn.currency)
        if txn.action is Action.PURCHASED:
            purchased_counts[key] = purchased_counts.get(key, 0) + 1
        elif txn.acquisition == AMBIGUOUS:
            ambiguous_sales.setdefault(key, []).append(txn)

    return {key: (sales, purchased_counts[key]) for key, sales in ambiguous_sales.items()}


def ambiguous_bounds(transactions: Iterable[Transaction]) -> dict[str, AmbiguousBounds]:
    """Per currency, the range of drop revenue possible among ambiguous sales.

    For an ambiguous item name, the lever is which `purchased`-many of its
    sale prices count as "matched to a purchase" (the rest are drop
    revenue) - purchase cost is fixed regardless of that choice, so sorting
    that item's sale prices gives the extremes: matching the
    highest-priced sales minimizes drop revenue, matching the
    lowest-priced ones maximizes it. Summed across every ambiguous item,
    this is a real bound consistent with the data, not a guess - see the
    "Confirmed vs Ambiguous Item Acquisition" design doc.

    Requires `classify` to have already been run - reads `.acquisition`.
    """
    totals: dict[str, dict[str, Decimal]] = {}
    for (_item_name, currency), (sales, purchased) in _ambiguous_groups(transactions).items():
        prices = sorted((sale.price for sale in sales), reverse=True)
        drop_count = len(prices) - purchased

        bucket = totals.setdefault(currency, {"min": Decimal("0"), "max": Decimal("0")})
        bucket["min"] += sum(prices[purchased:], Decimal("0"))
        bucket["max"] += sum(prices[:drop_count], Decimal("0"))

    return {
        currency: AmbiguousBounds(
            currency=currency,
            drop_revenue_min=values["min"],
            drop_revenue_max=values["max"],
        )
        for currency, values in totals.items()
    }


def ambiguous_best_guess(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    """Per currency, a single FIFO-convention best guess at ambiguous drop revenue (SMHT-10).

    A documented convention, not a recovered fact - the same honesty
    standard `pairing.py`'s FIFO win-rate pairing already applies to a
    different question (see that module's docstring): for each ambiguous
    item, the oldest purchases are paired to the oldest sales (FIFO, by
    `order_index` - 0 is most recent, so a *larger* `order_index` is
    older); the `sold - purchased` most-recent, unpaired sales are the
    guessed drops. Deliberately independent of `ambiguous_bounds`'
    min/max above, which instead sorts by *price* to find the extremes
    consistent with the data - this sorts by *time* to produce one
    specific, plausible guess instead of a range.

    Requires `classify` to have already been run - reads `.acquisition`.
    """
    totals: dict[str, Decimal] = {}
    for (_item_name, currency), (sales, purchased) in _ambiguous_groups(transactions).items():
        oldest_first = sorted(sales, key=lambda t: t.order_index, reverse=True)
        guessed_drops = oldest_first[purchased:]
        totals[currency] = totals.get(currency, Decimal("0")) + sum(
            (sale.price for sale in guessed_drops), Decimal("0")
        )
    return totals


def ambiguous_contributions(transactions: Iterable[Transaction]) -> dict[int, tuple[Decimal, Decimal]]:
    """`order_index` -> (max contribution, best-guess contribution), per ambiguous sale.

    The per-transaction breakdown behind `ambiguous_bounds`' max bucket and
    `ambiguous_best_guess`'s FIFO bucket above, keyed by each transaction's
    own `order_index` (globally unique - Steam's own row position in the
    export) instead of aggregated to one currency total. Lets a caller
    building a running total over time (`stats.cumulative_series`) look up
    each transaction's own contribution as it's encountered chronologically,
    without re-deriving whole-history bucket membership itself - bucket
    membership depends on a sale's price/order relative to *every* other
    sale of that item, past or future, so it can't be computed
    incrementally during the chronological walk alone. No `min` variant -
    nothing downstream needs a running min line yet.

    Requires `classify` to have already been run - reads `.acquisition`.
    """
    contributions: dict[int, tuple[Decimal, Decimal]] = {}
    for (_item_name, _currency), (sales, purchased) in _ambiguous_groups(transactions).items():
        drop_count = len(sales) - purchased

        by_price_desc = sorted(sales, key=lambda t: (t.price, t.order_index), reverse=True)
        max_bucket = {sale.order_index for sale in by_price_desc[:drop_count]}

        oldest_first = sorted(sales, key=lambda t: t.order_index, reverse=True)
        best_guess_bucket = {sale.order_index for sale in oldest_first[purchased:]}

        for sale in sales:
            contributions[sale.order_index] = (
                sale.price if sale.order_index in max_bucket else Decimal("0"),
                sale.price if sale.order_index in best_guess_bucket else Decimal("0"),
            )
    return contributions
