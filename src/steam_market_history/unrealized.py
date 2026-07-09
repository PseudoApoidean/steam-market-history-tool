from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .models import Action, Transaction


@dataclass(frozen=True, slots=True)
class UnrealizedItem:
    item_name: str
    currency: str
    held_count: int
    current_value: Decimal
    gain_min: Decimal
    gain_max: Decimal


def compute_unrealized(
    transactions: Iterable[Transaction], prices: dict[str, Decimal]
) -> tuple[dict[str, UnrealizedItem], list[str]]:
    """Per item name, the range of unrealized gain for currently-held units.

    "Held" means purchased more times than sold - the same per-item-name
    reconciliation as `acquisition.py`, mirrored (that finds excess
    sales; this finds excess purchases). Not sharing code with
    `acquisition.py` despite the conceptual mirror: the actual counting
    is a handful of lines, and this needs individual purchase prices for
    the bound computation below, which `acquisition.py` doesn't - a
    shared abstraction isn't worth it yet for that little code.

    Which *specific* `held_count` purchases remain unsold can't be known
    (no unique per-item identifier - see "Export Data Format"), so like
    SMHT-1's confirmed/ambiguous design, this reports a range rather than
    guessing: `gain_max` assumes the cheapest `held_count` purchases are
    the ones still held (minimizing cost basis); `gain_min` assumes the
    most expensive ones are (maximizing it). `current_value` itself is
    exact (from the supplied price, not guessed) - only the cost-basis
    side of the calculation is a range.

    Returns `(per-item results, item names that are held but have no
    price in prices)` - the second so a caller can report an honest "N
    held items have no price, this total is partial" instead of silently
    under-counting.
    """
    purchases_by_item: dict[str, list[Transaction]] = {}
    sold_counts: dict[str, int] = {}
    for txn in transactions:
        if txn.action is Action.PURCHASED:
            purchases_by_item.setdefault(txn.item_name, []).append(txn)
        else:
            sold_counts[txn.item_name] = sold_counts.get(txn.item_name, 0) + 1

    results: dict[str, UnrealizedItem] = {}
    missing_prices: list[str] = []

    for item_name, purchases in purchases_by_item.items():
        held_count = len(purchases) - sold_counts.get(item_name, 0)
        if held_count <= 0:
            continue
        if item_name not in prices:
            missing_prices.append(item_name)
            continue

        current_value = prices[item_name] * held_count
        sorted_desc = sorted((p.price for p in purchases), reverse=True)
        cost_basis_max = sum(sorted_desc[:held_count], Decimal("0"))
        cost_basis_min = sum(sorted_desc[-held_count:], Decimal("0"))

        results[item_name] = UnrealizedItem(
            item_name=item_name,
            currency=purchases[0].currency,
            held_count=held_count,
            current_value=current_value,
            gain_min=current_value - cost_basis_max,
            gain_max=current_value - cost_basis_min,
        )

    return results, sorted(missing_prices)
