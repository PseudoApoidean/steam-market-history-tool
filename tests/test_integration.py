from pathlib import Path

from steam_market_history.filters import filter_by_queries, parse_query
from steam_market_history.parser import load_history_json, parse_transactions
from steam_market_history.stats import summarize

FIXTURE = Path(__file__).parent / "fixtures" / "sample_history.json"


def test_counter_strike_crate_filter_end_to_end() -> None:
    """The tool's motivating use case: lifetime profit from selling CS2 crates
    specifically, not every CS2 item and not crates sold from other games."""
    transactions = parse_transactions(load_history_json(FIXTURE))

    query = parse_query("game:CSGO||CS2||Counter-Strike 2 name:*Case")
    result = filter_by_queries(transactions, [query])

    # Fixture also has a Team Fortress 2 "Fire & Ice Case" (wrong game) and a
    # Rust purchase (wrong game and wrong action) — neither should match.
    assert [t.item_name for t in result] == ["Kilowatt Case"]

    totals = summarize(result)
    assert totals["£"].net_profit == totals["£"].sold_total
    assert totals["£"].purchased_count == 0
