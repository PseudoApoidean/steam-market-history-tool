"""Regenerates tests/fixtures/multi_currency_history.json.

One currency per market type (4 games, 4 currencies, one each) - covers the
common real-world shape (a single account's history typically has one
currency per game/market type) with enough variety to exercise confirmed
drops, a real matched trade, an ambiguous acquisition case, and a
still-held item, not just currency separation. See
generate_multi_currency_stress_fixture.py for the harder case, every
market type in every currency.

Run from the repo root: python scripts/generate_multi_currency_fixture.py
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

# (currency, action, item_name, game_name, price_amount, acted_on, listed_on)
TRANSACTIONS = [
    # British Pounds - Counter-Strike 2 - mostly confirmed drops (sold, never bought)
    ("£", "Sold", "Kilowatt Case", "Counter-Strike 2", "0.17", "19 Jun", "19 Jun"),
    ("£", "Sold", "Kilowatt Case", "Counter-Strike 2", "0.19", "12 Jun", "12 Jun"),
    ("£", "Purchased", "Fracture Case", "Counter-Strike 2", "0.35", "3 Jun", "3 Jun"),
    ("£", "Sold", "Fracture Case", "Counter-Strike 2", "0.52", "20 Jun", "18 Jun"),
    # Euros - Rust - real matched trade plus an ambiguous case (2 sold, 1 bought)
    ("€", "Purchased", "Metal Facemask", "Rust", "3.50", "1 May", "1 May"),
    ("€", "Sold", "Metal Facemask", "Rust", "5.10", "15 May", "14 May"),
    ("€", "Sold", "Road Sign Jacket", "Rust", "2.20", "2 Jun", "2 Jun"),
    ("€", "Sold", "Road Sign Jacket", "Rust", "1.95", "9 Jun", "9 Jun"),
    ("€", "Purchased", "Road Sign Jacket", "Rust", "1.40", "20 May", "20 May"),
    # US Dollars - PUBG - simple purchase/sale pairs
    ("$", "Purchased", "Level 3 Backpack", "PUBG: BATTLEGROUNDS", "1.10", "4 Apr", "4 Apr"),
    ("$", "Sold", "Level 3 Backpack", "PUBG: BATTLEGROUNDS", "1.75", "22 Apr", "21 Apr"),
    ("$", "Purchased", "Gasmask", "PUBG: BATTLEGROUNDS", "0.60", "6 Apr", "6 Apr"),
    ("$", "Sold", "Gasmask", "PUBG: BATTLEGROUNDS", "0.45", "10 Apr", "10 Apr"),
    # Japanese Yen - Team Fortress 2 - a fourth currency, still held (purchased only)
    ("¥", "Sold", "Team Captain", "Team Fortress 2", "150", "1 Mar", "1 Mar"),
    ("¥", "Purchased", "Ellis' Cap", "Team Fortress 2", "80", "5 Mar", "5 Mar"),
    ("¥", "Sold", "Ellis' Cap", "Team Fortress 2", "120", "18 Mar", "17 Mar"),
]


def build_payload() -> dict:
    rows = []
    for i, (currency, action, item_name, game_name, amount, acted_on, listed_on) in enumerate(
        TRANSACTIONS
    ):
        row_id = f"history_row_{600000000000000000 + i * 2}_{600000000000000000 + i * 2 + 1}"
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
        "total_count": len(TRANSACTIONS),
        "assets": {},
        "hovers": "",
        "results_html": "".join(rows),
    }


if __name__ == "__main__":
    out_path = Path(__file__).parent.parent / "tests" / "fixtures" / "multi_currency_history.json"
    out_path.write_text(json.dumps(build_payload(), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(TRANSACTIONS)} transactions to {out_path}")
