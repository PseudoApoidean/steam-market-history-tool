from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Action(str, Enum):
    SOLD = "sold"
    PURCHASED = "purchased"


@dataclass(frozen=True, slots=True)
class Transaction:
    """A single Steam Community Market history entry.

    `order_index` preserves the row's position in Steam's export (0 = most
    recent). Steam's history page doesn't include a year in `acted_on` /
    `listed_on`, so real chronological ordering across year boundaries isn't
    recoverable from this data alone; `order_index` is the only reliable
    ordering signal.
    """

    order_index: int
    action: Action
    item_name: str
    game_name: str
    price: Decimal
    currency: str
    acted_on: str
    listed_on: str
