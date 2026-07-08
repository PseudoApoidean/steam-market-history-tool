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
    assert payload == {"ok": True, "totals": {}, "by_game": {}}


def test_list_games_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--list-games", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True,
        "games": ["Counter-Strike 2", "Rust", "Team Fortress 2"],
    }


def test_missing_file_reports_structured_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = main([str(tmp_path / "does-not-exist.json"), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


def test_text_output_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([FIXTURE, "--by-game"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Lifetime profit/loss:" in out
    assert "By game:" in out
    assert "Counter-Strike 2:" in out
