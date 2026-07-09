from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from .models import Action, Transaction

DROP = "drop"
AMBIGUOUS = "ambiguous"
PURCHASED = "purchased"


def classify(transactions: Sequence[Transaction]) -> list[Transaction]:
    """Label each transaction's `acquisition`, per item name.

    Per item name, with `purchased` = purchase count and `sold` = sale
    count:

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
    counts: dict[str, tuple[int, int]] = {}
    for txn in transactions:
        purchased, sold = counts.get(txn.item_name, (0, 0))
        if txn.action is Action.PURCHASED:
            counts[txn.item_name] = (purchased + 1, sold)
        else:
            counts[txn.item_name] = (purchased, sold + 1)

    result = []
    for txn in transactions:
        if txn.action is Action.PURCHASED:
            result.append(txn)
            continue
        purchased, sold = counts[txn.item_name]
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
    ambiguous_sales: dict[str, list[Transaction]] = {}
    purchased_counts: dict[str, int] = {}
    for txn in transactions:
        if txn.action is Action.PURCHASED:
            purchased_counts[txn.item_name] = purchased_counts.get(txn.item_name, 0) + 1
        elif txn.acquisition == AMBIGUOUS:
            ambiguous_sales.setdefault(txn.item_name, []).append(txn)

    totals: dict[str, dict[str, Decimal]] = {}
    for item_name, sales in ambiguous_sales.items():
        purchased = purchased_counts[item_name]
        prices = sorted((sale.price for sale in sales), reverse=True)
        drop_count = len(prices) - purchased

        currency = sales[0].currency
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
