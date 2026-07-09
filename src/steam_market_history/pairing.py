from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .models import Action, Transaction


@dataclass(frozen=True, slots=True)
class TradePair:
    item_name: str
    currency: str
    purchase_price: Decimal
    sale_price: Decimal

    @property
    def profit(self) -> Decimal:
        return self.sale_price - self.purchase_price


def fifo_pairs(transactions: Iterable[Transaction]) -> list[TradePair]:
    """Pair purchases to sales per item name, FIFO by `order_index`.

    The oldest unmatched purchase of an item pairs with the oldest
    unmatched sale of that item. This is a documented convention, not a
    fact recovered from the data - Steam's export has no way to know which
    specific unit was sold for which specific purchase (see "no unique
    per-item/listing identifier" in the "Export Data Format" doc). Excess
    sales beyond the number of purchases (drops - see `acquisition.py`) or
    excess purchases (still-held items) are left unpaired.

    Unlike `acquisition.classify`'s confirmed/ambiguous split, a single
    FIFO convention is appropriate here: this function's entire purpose is
    to produce paired trades for a win-rate count, and the convention is
    stated plainly as a convention rather than presented as a recovered
    fact - a different situation from silently picking one pairing to
    report a £ split as though it were certain.
    """
    by_item: dict[str, list[Transaction]] = {}
    for txn in transactions:
        by_item.setdefault(txn.item_name, []).append(txn)

    pairs: list[TradePair] = []
    for item_txns in by_item.values():
        purchases = sorted(
            (t for t in item_txns if t.action is Action.PURCHASED),
            key=lambda t: t.order_index,
            reverse=True,
        )
        sales = sorted(
            (t for t in item_txns if t.action is Action.SOLD),
            key=lambda t: t.order_index,
            reverse=True,
        )
        for purchase, sale in zip(purchases, sales):
            pairs.append(
                TradePair(
                    item_name=purchase.item_name,
                    currency=sale.currency,
                    purchase_price=purchase.price,
                    sale_price=sale.price,
                )
            )
    return pairs
