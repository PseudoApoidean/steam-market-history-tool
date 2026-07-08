from decimal import Decimal

import pytest

from steam_market_history.money import PriceParseError, parse_price


@pytest.mark.parametrize(
    ("raw", "amount", "currency"),
    [
        ("£0.17", Decimal("0.17"), "£"),
        ("£1.55", Decimal("1.55"), "£"),
        ("0,04€", Decimal("0.04"), "€"),
        ("2,--€", Decimal("2.00"), "€"),
        ("6,--€", Decimal("6.00"), "€"),
        ("$12,345.67", Decimal("12345.67"), "$"),
        ("1.234,56€", Decimal("1234.56"), "€"),
    ],
)
def test_parse_price(raw: str, amount: Decimal, currency: str) -> None:
    parsed_amount, parsed_currency = parse_price(raw)
    assert parsed_amount == amount
    assert parsed_currency == currency


def test_parse_price_rejects_missing_currency() -> None:
    with pytest.raises(PriceParseError):
        parse_price("1.55")
