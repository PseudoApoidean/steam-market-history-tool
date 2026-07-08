from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_PRICE_RE = re.compile(r"^([^\d\s,.\-]+)?\s*([\d.,\-]+)\s*([^\d\s,.\-]+)?$")


class PriceParseError(ValueError):
    """Raised when a price string can't be parsed into an amount + currency."""


def parse_price(raw: str) -> tuple[Decimal, str]:
    """Parse a Steam market price string into (amount, currency_symbol).

    Steam's history mixes formats depending on account currency/locale, e.g.:
      "£1.55"  -> (Decimal("1.55"), "£")   # symbol first, period decimal
      "0,04€"  -> (Decimal("0.04"), "€")   # symbol last, comma decimal
      "2,--€"  -> (Decimal("2.00"), "€")   # German-style whole-amount shorthand
    """
    text = raw.strip()
    match = _PRICE_RE.match(text)
    if not match:
        raise PriceParseError(f"unrecognized price format: {raw!r}")

    leading, number, trailing = match.groups()
    currency = leading or trailing
    if not currency:
        raise PriceParseError(f"no currency symbol found in: {raw!r}")

    number = number.replace("--", "00")

    if "," in number and "." in number:
        if number.rindex(",") > number.rindex("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif "," in number:
        number = number.replace(",", ".")

    try:
        amount = Decimal(number)
    except InvalidOperation as exc:
        raise PriceParseError(f"could not parse numeric amount from: {raw!r}") from exc

    return amount, currency
