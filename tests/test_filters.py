from decimal import Decimal

from steam_market_history.filters import filter_by_games, unique_game_names
from steam_market_history.models import Action, Transaction


def _txn(order_index: int, game_name: str, action: Action = Action.SOLD) -> Transaction:
    return Transaction(
        order_index=order_index,
        action=action,
        item_name=f"item-{order_index}",
        game_name=game_name,
        price=Decimal("1.00"),
        currency="£",
        acted_on="1 Jan",
        listed_on="1 Jan",
    )


def test_whitelist_keeps_only_listed_games() -> None:
    txns = [_txn(0, "Rust"), _txn(1, "Counter-Strike 2"), _txn(2, "Team Fortress 2")]

    result = filter_by_games(txns, whitelist=["Rust", "Team Fortress 2"])

    assert {t.game_name for t in result} == {"Rust", "Team Fortress 2"}


def test_blacklist_drops_listed_games() -> None:
    txns = [_txn(0, "Rust"), _txn(1, "Counter-Strike 2")]

    result = filter_by_games(txns, blacklist=["Rust"])

    assert [t.game_name for t in result] == ["Counter-Strike 2"]


def test_whitelist_and_blacklist_combine() -> None:
    txns = [_txn(0, "Rust"), _txn(1, "Counter-Strike 2"), _txn(2, "Team Fortress 2")]

    result = filter_by_games(txns, whitelist=["Rust", "Team Fortress 2"], blacklist=["Rust"])

    assert [t.game_name for t in result] == ["Team Fortress 2"]


def test_matching_is_case_insensitive() -> None:
    txns = [_txn(0, "Counter-Strike 2")]

    result = filter_by_games(txns, whitelist=["counter-strike 2"])

    assert len(result) == 1


def test_unique_game_names_sorted() -> None:
    txns = [_txn(0, "Rust"), _txn(1, "Counter-Strike 2"), _txn(2, "Rust")]

    assert unique_game_names(txns) == ["Counter-Strike 2", "Rust"]
