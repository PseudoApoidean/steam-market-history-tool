"""Regenerates tests/fixtures/multi_currency_stress_history.json.

Every market type in every currency, deliberately unrealistic (a real
account has one currency, not four) - stresses the "currencies are never
mixed" design principle specifically, rather than covering a realistic
account shape (see generate_multi_currency_fixture.py for that).

Every (game, currency) pair gets exactly one purchase (1.00) and one sale
(2.50) of two different items, so every one of the resulting 16 buckets
has the same predictable shape (sold_count=1, purchased_count=1, net=1.50)
- makes cross-currency-separation bugs (mixed totals, dropped buckets,
wrong game attribution) trivial to assert against directly.

Run from the repo root: python scripts/generate_multi_currency_stress_fixture.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path

_ROW_TEMPLATE = """<div class="market_listing_row market_recent_listing_row" id="{row_id}">
    <div class="market_listing_left_cell market_listing_gainorloss">
    {sign}    </div>
    <img id="{row_id}_image" src="https://example.com/img.jpg" class="market_listing_item_img" alt="" />
    <div class="market_listing_right_cell market_listing_their_price">
    <span class="market_table_value">
        <span class="market_listing_price">
                        {price}                    </span>
        <br/>
                                                                    </span>
    </div>
    <div class="market_listing_right_cell market_listing_listed_date can_combine">
        {acted_on}    </div>
    <div class="market_listing_right_cell market_listing_listed_date can_combine">
        {listed_on}    </div>
    <div class="market_listing_right_cell market_listing_whoactedwith">

        <div class="market_listing_whoactedwith_name_block">
        </div>
    </div>

        <div class="market_listing_item_name_block">
        <span id="{row_id}_name" class="market_listing_item_name" style="color: #b0c3d9;">{item_name}</span>
        <br/>            <span class="market_listing_game_name">{game_name}</span>
                <div class="market_listing_listed_date_combined">
            {action}: {acted_on}        </div>
    </div>
    <div style="clear: both"></div>
</div>
"""

CURRENCIES = ["£", "€", "$", "¥"]
GAMES = ["Counter-Strike 2", "Rust", "PUBG: BATTLEGROUNDS", "Team Fortress 2"]


def _build_transactions() -> list[tuple[str, str, str, str, str, str, str]]:
    transactions = []
    day = 1
    for game in GAMES:
        for currency in CURRENCIES:
            acted_on = f"{day} Jan"
            transactions.append(
                (currency, "Purchased", f"{game} Bought Item", game, "1.00", acted_on, acted_on)
            )
            day += 1
            acted_on = f"{day} Jan"
            transactions.append(
                (currency, "Sold", f"{game} Sold Item", game, "2.50", acted_on, acted_on)
            )
            day += 1
    return transactions


def build_payload() -> dict:
    transactions = _build_transactions()
    rows = []
    for i, (currency, action, item_name, game_name, amount, acted_on, listed_on) in enumerate(
        transactions
    ):
        row_id = f"history_row_{700000000000000000 + i * 2}_{700000000000000000 + i * 2 + 1}"
        price = f"{currency}{amount}" if currency != "€" else f"{amount}{currency}"
        sign = "-" if action == "Sold" else "+"
        rows.append(
            _ROW_TEMPLATE.format(
                row_id=row_id,
                sign=sign,
                price=html.escape(price),
                acted_on=acted_on,
                listed_on=listed_on,
                item_name=html.escape(item_name),
                game_name=html.escape(game_name),
                action=action,
            )
        )

    return {
        "success": True,
        "pagesize": 500,
        "start": 0,
        "total_count": len(transactions),
        "assets": {},
        "hovers": "",
        "results_html": "".join(rows),
    }


if __name__ == "__main__":
    out_path = (
        Path(__file__).parent.parent / "tests" / "fixtures" / "multi_currency_stress_history.json"
    )
    payload = build_payload()
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {payload['total_count']} transactions to {out_path}")
