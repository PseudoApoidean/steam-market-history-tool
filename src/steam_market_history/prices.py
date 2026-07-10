from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


class PriceFileError(ValueError):
    """Raised when a supplied price file can't be parsed."""


def load_price_file(path: str | Path) -> dict[str, Decimal]:
    """Load a user-supplied `{item_name: current_price}` JSON file.

    This is the *only* source of current market value this tool ever
    uses - no network calls, full stop (see the "no parsing dependencies"
    design principle, which extends to "no network dependencies" here).
    Live price-fetching, if it ever exists, happens entirely outside this
    tool (e.g. in `steam-market-ledger`'s GUI), which would write the
    result to a file in this exact shape and point this tool at it - this
    tool can't tell, and doesn't need to know, whether a price was typed
    by hand or fetched a second ago.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PriceFileError(f"could not read price file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PriceFileError(f"price file is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise PriceFileError("price file must be a JSON object of {item_name: price}")

    prices: dict[str, Decimal] = {}
    for item_name, price in raw.items():
        try:
            prices[item_name] = Decimal(str(price))
        except InvalidOperation as exc:
            raise PriceFileError(f"invalid price for {item_name!r}: {price!r}") from exc
    return prices
