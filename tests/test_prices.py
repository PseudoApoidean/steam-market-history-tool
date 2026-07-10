import json
from decimal import Decimal
from pathlib import Path

import pytest

from steam_market_history.prices import PriceFileError, load_price_file


def test_load_price_file_parses_item_name_to_decimal(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"Kilowatt Case": "0.19", "Metal Facemask": "3.5"}))

    prices = load_price_file(path)

    assert prices == {
        "Kilowatt Case": Decimal("0.19"),
        "Metal Facemask": Decimal("3.5"),
    }


def test_load_price_file_accepts_numeric_json_values(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"Kilowatt Case": 0.19}))

    prices = load_price_file(path)

    assert prices["Kilowatt Case"] == Decimal("0.19")


def test_load_price_file_missing_file_raises_price_file_error(tmp_path: Path) -> None:
    with pytest.raises(PriceFileError):
        load_price_file(tmp_path / "does-not-exist.json")


def test_load_price_file_invalid_json_raises_price_file_error(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text("{not valid json")

    with pytest.raises(PriceFileError):
        load_price_file(path)


def test_load_price_file_non_object_raises_price_file_error(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(["not", "an", "object"]))

    with pytest.raises(PriceFileError):
        load_price_file(path)


def test_load_price_file_invalid_price_value_raises_price_file_error(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"Kilowatt Case": "not-a-number"}))

    with pytest.raises(PriceFileError):
        load_price_file(path)
