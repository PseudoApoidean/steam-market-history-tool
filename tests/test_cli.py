import json
from pathlib import Path

import pytest

from steam_market_history.cli import main

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_history.json")


def test_json_output_totals_and_by_game(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["totals"]["£"]["sold_count"] == 1
    assert payload["totals"]["£"]["purchased_count"] == 1
    assert payload["by_game"]["Counter-Strike 2"]["£"]["net_profit"] == "0.17"
    assert payload["series"]["£"][-1]["cumulative_net_profit"] == payload["totals"]["£"]["net_profit"]


def test_json_output_includes_by_item(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["by_item"]["Kilowatt Case"]["£"]["net_profit"] == "0.17"
    # by_item and by_game are different groupings of the same data - not
    # the same keys, both present simultaneously.
    assert "Kilowatt Case" not in payload["by_game"]
    assert "Counter-Strike 2" not in payload["by_item"]


def test_json_output_series_is_ordered_oldest_first(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    points = payload["series"]["£"]
    order_indices = [point["order_index"] for point in points]
    assert order_indices == sorted(order_indices, reverse=True)
    assert all("acted_on" in point for point in points)


def test_json_output_respects_filter(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--filter", "game:Counter-Strike 2 name:*Case", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert list(payload["by_game"].keys()) == ["Counter-Strike 2"]


def test_json_output_invalid_filter_reports_structured_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([FIXTURE, "--filter", "bogus", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "error" in payload


def test_json_output_no_matches_is_still_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--filter", "game:NoSuchGame", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True,
        "totals": {},
        "by_game": {},
        "by_item": {},
        "series": {},
        "acquisition": {},
        "win_rate": {},
        "unrealized": {},
        "unrealized_missing_prices": [],
    }


def test_list_games_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--list-games", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    # "Fire & Ice Case" is appid 753 in the fixture, so its game_name is
    # corrected to "Steam" rather than the raw "Team Fortress 2" - see
    # test_parser.py.
    assert payload == {
        "ok": True,
        "games": ["Counter-Strike 2", "Rust", "Steam"],
    }


def test_json_output_includes_acquisition_summary(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    # Both fixture sales ("Kilowatt Case", "Fire & Ice Case") have no
    # purchase of the same item name at all - confirmed drops, not
    # ambiguous. See test_acquisition.py for the ambiguous-bucket cases.
    gbp = payload["acquisition"]["£"]
    assert gbp["confirmed_drop_count"] == 1
    assert gbp["confirmed_drop_revenue"] == "0.17"
    assert gbp["ambiguous_count"] == 0
    eur = payload["acquisition"]["€"]
    assert eur["confirmed_drop_count"] == 1
    assert eur["confirmed_drop_revenue"] == "2.00"


def test_json_output_includes_win_rate_key(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    # No item in the fixture has both a purchase and a sale of the same
    # name, so there are no FIFO pairs at all - empty, not missing.
    assert payload["win_rate"] == {}


def test_missing_file_reports_structured_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = main([str(tmp_path / "does-not-exist.json"), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


def test_json_output_without_price_file_has_empty_unrealized(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([FIXTURE, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unrealized"] == {}
    assert payload["unrealized_missing_prices"] == []


def test_json_output_with_price_file_reports_unrealized_gain(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    # "Rat-a-tat-tat Thompson" is the fixture's only item purchased and
    # never sold (£1.55) - the sole held item.
    price_file = tmp_path / "prices.json"
    price_file.write_text(json.dumps({"Rat-a-tat-tat Thompson": "3.00"}))

    exit_code = main([FIXTURE, "--price-file", str(price_file), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    gbp = payload["unrealized"]["£"]
    assert gbp["held_count"] == 1
    assert gbp["current_value"] == "3.00"
    assert gbp["gain_min"] == gbp["gain_max"] == "1.45"
    assert payload["unrealized_missing_prices"] == []


def test_json_output_with_price_file_reports_missing_prices(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    price_file = tmp_path / "prices.json"
    price_file.write_text(json.dumps({}))

    exit_code = main([FIXTURE, "--price-file", str(price_file), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unrealized"] == {}
    assert payload["unrealized_missing_prices"] == ["Rat-a-tat-tat Thompson"]


def test_json_output_invalid_price_file_reports_structured_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    price_file = tmp_path / "prices.json"
    price_file.write_text("{not valid json")

    exit_code = main([FIXTURE, "--price-file", str(price_file), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "error" in payload


def test_text_output_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--by-game"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Lifetime profit/loss:" in out
    assert "By game:" in out
    assert "Counter-Strike 2:" in out
