from decimal import Decimal

import pytest

from steam_market_history.filters import (
    FilterQueryError,
    filter_by_queries,
    match_query,
    parse_query,
    unique_game_names,
)
from steam_market_history.models import Action, Transaction


def _txn(
    order_index: int,
    game_name: str,
    item_name: str = "item",
    action: Action = Action.SOLD,
    acquisition: str = "purchased",
    category: str | None = None,
) -> Transaction:
    return Transaction(
        order_index=order_index,
        action=action,
        item_name=item_name,
        game_name=game_name,
        price=Decimal("1.00"),
        currency="£",
        acted_on="1 Jan",
        listed_on="1 Jan",
        acquisition=acquisition,
        category=category,
    )


def test_single_clause_matches_field() -> None:
    query = parse_query("game:Rust")

    assert match_query(_txn(0, "Rust"), query)
    assert not match_query(_txn(0, "Counter-Strike 2"), query)


def test_or_within_a_clause() -> None:
    query = parse_query("game:CSGO||CS2")

    assert match_query(_txn(0, "CSGO"), query)
    assert match_query(_txn(0, "CS2"), query)
    assert not match_query(_txn(0, "Rust"), query)


def test_and_across_clauses() -> None:
    query = parse_query("game:CS2 name:*Case")

    assert match_query(_txn(0, "CS2", item_name="Kilowatt Case"), query)
    assert not match_query(_txn(0, "CS2", item_name="Sticker"), query)
    assert not match_query(_txn(0, "Rust", item_name="Kilowatt Case"), query)


def test_negation() -> None:
    query = parse_query("!game:Rust")

    assert match_query(_txn(0, "CS2"), query)
    assert not match_query(_txn(0, "Rust"), query)


def test_matching_is_case_insensitive() -> None:
    query = parse_query("game:cs2 name:*case")

    assert match_query(_txn(0, "CS2", item_name="Kilowatt Case"), query)


def test_clause_value_may_contain_spaces() -> None:
    query = parse_query("game:Counter-Strike 2 name:*Case")

    assert match_query(_txn(0, "Counter-Strike 2", item_name="Kilowatt Case"), query)
    assert not match_query(_txn(0, "Counter-Strike 2 Trading Card", item_name="foo"), query)


def test_or_list_may_include_a_multi_word_pattern() -> None:
    query = parse_query("game:CSGO||CS2||Counter-Strike 2")

    assert match_query(_txn(0, "CSGO"), query)
    assert match_query(_txn(0, "Counter-Strike 2"), query)
    assert not match_query(_txn(0, "Rust"), query)


def test_category_clause_matches_field() -> None:
    query = parse_query("category:Trading Card")

    assert match_query(_txn(0, "Steam", category="Trading Card"), query)
    assert not match_query(_txn(0, "Steam", category="Emoticon"), query)


def test_category_clause_on_a_transaction_with_no_category_does_not_raise() -> None:
    query = parse_query("category:Trading Card")

    assert not match_query(_txn(0, "Counter-Strike 2", category=None), query)


def test_counter_strike_crate_filter() -> None:
    """The motivating use case: profit from selling CS2/CSGO crates specifically,
    not every CS2 item and not crates from unrelated games."""
    query = parse_query("game:CSGO||CS2||Counter-Strike 2 name:*Case")

    assert match_query(_txn(0, "Counter-Strike 2", item_name="Kilowatt Case"), query)
    assert match_query(_txn(0, "CSGO", item_name="Operation Bravo Case"), query)
    assert not match_query(_txn(0, "Counter-Strike 2", item_name="Sticker | iBUYPOWER"), query)
    assert not match_query(_txn(0, "Team Fortress 2", item_name="Mann Co. Supply Case"), query)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "game", "notafield:Rust", "game:"],
)
def test_parse_query_rejects_invalid_syntax(text: str) -> None:
    with pytest.raises(FilterQueryError):
        parse_query(text)


def test_filter_by_queries_ors_multiple_queries() -> None:
    txns = [
        _txn(0, "CS2", item_name="Kilowatt Case"),
        _txn(1, "Rust", item_name="Skin"),
        _txn(2, "Team Fortress 2", item_name="Hat"),
    ]

    queries = [parse_query("game:CS2 name:*Case"), parse_query("game:Rust")]
    result = filter_by_queries(txns, queries)

    assert [t.order_index for t in result] == [0, 1]


def test_filter_by_queries_with_no_queries_returns_everything() -> None:
    txns = [_txn(0, "CS2"), _txn(1, "Rust")]

    assert filter_by_queries(txns, []) == txns


def test_acquisition_clause_matches_field() -> None:
    query = parse_query("acquisition:drop")

    assert match_query(_txn(0, "Rust", acquisition="drop"), query)
    assert not match_query(_txn(0, "Rust", acquisition="purchased"), query)
    assert not match_query(_txn(0, "Rust", acquisition="ambiguous"), query)


def test_any_keyword_matches_regardless_of_field_value() -> None:
    query = parse_query("acquisition:any")

    assert match_query(_txn(0, "Rust", acquisition="drop"), query)
    assert match_query(_txn(0, "Rust", acquisition="purchased"), query)
    assert match_query(_txn(0, "Rust", acquisition="ambiguous"), query)


def test_any_keyword_is_case_insensitive_and_works_on_any_field() -> None:
    query = parse_query("game:ANY")

    assert match_query(_txn(0, "Rust"), query)
    assert match_query(_txn(0, "Counter-Strike 2"), query)


def test_any_keyword_negated_matches_nothing() -> None:
    query = parse_query("!acquisition:any")

    assert not match_query(_txn(0, "Rust", acquisition="drop"), query)
    assert not match_query(_txn(0, "Rust", acquisition="purchased"), query)


def test_unique_game_names_sorted() -> None:
    txns = [_txn(0, "Rust"), _txn(1, "Counter-Strike 2"), _txn(2, "Rust")]

    assert unique_game_names(txns) == ["Counter-Strike 2", "Rust"]
