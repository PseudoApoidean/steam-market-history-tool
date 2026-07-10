"""Regenerates tests/fixtures/drop_lines_history.json.

Single currency, single game, deliberately built for a *wide* spread between
the confirmed-drop floor, the worst-case ambiguous ceiling, and the FIFO
best-guess line (SMHT-8/SMHT-10) - the three lines steam-market-ledger's
SML-33 draws on its profit chart. Earlier manual GUI testing of that
feature used data with only a narrow confirmed-vs-ambiguous spread, which
left it unclear whether the hatched min/max band was even visible; this
fixture exists so that can be checked against a real, wide gap instead.

Three items, one currency (£), one game (Counter-Strike 2):
- "CS Case": sold 3x, never bought - a pure confirmed drop, contributes
  only to the floor (min) line.
- "Rare Sticker Capsule": bought once (£2.00), sold 3x at wildly different
  prices (£12.00, £0.50, £5.00, in that chronological order) - ambiguous
  (sold > purchased by 2). FIFO best-guess excludes the *oldest* sale
  (£12.00, matched to the one purchase) from drops, leaving £0.50+£5.00 =
  £5.50 as the guessed drop revenue. The worst-case ceiling instead
  excludes the *lowest-priced* sale (£0.50) and keeps the two highest
  (£12.00+£5.00 = £17.00) - deliberately ordered so FIFO and worst-case
  diverge, not just coincide.
- "Trade Knife": one matched purchase/sale pair, a real trade with no
  drop/ambiguous classification at all - gives Include/Exclude/Only
  something to actually differ on.

Expected final cumulative totals (asserted in test_drop_lines_fixture.py):
confirmed floor = £0.45 (0.10+0.15+0.20), worst-case ceiling = £17.45
(0.45+17.00), FIFO best guess = £5.95 (0.45+5.50) - a floor-to-ceiling
spread of about 39x, chosen to be unmistakable at any chart scale.

Run from the repo root: python scripts/generate_drop_lines_fixture.py
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
# Listed newest-first (row 0 = order_index 0 = most recent), matching
# Steam's own export order - see each item's docstring paragraph above for
# the chronological (oldest-first) story this reverses.
TRANSACTIONS = [
    ("£", "Sold", "CS Case", "Counter-Strike 2", "0.20", "24 May", "24 May"),
    ("£", "Sold", "Trade Knife", "Counter-Strike 2", "1.50", "20 May", "20 May"),
    ("£", "Purchased", "Trade Knife", "Counter-Strike 2", "1.00", "16 May", "16 May"),
    ("£", "Sold", "Rare Sticker Capsule", "Counter-Strike 2", "5.00", "14 May", "14 May"),
    ("£", "Sold", "CS Case", "Counter-Strike 2", "0.15", "10 May", "10 May"),
    ("£", "Sold", "Rare Sticker Capsule", "Counter-Strike 2", "0.50", "8 May", "8 May"),
    ("£", "Sold", "CS Case", "Counter-Strike 2", "0.10", "5 May", "5 May"),
    ("£", "Sold", "Rare Sticker Capsule", "Counter-Strike 2", "12.00", "3 May", "3 May"),
    ("£", "Purchased", "Rare Sticker Capsule", "Counter-Strike 2", "2.00", "1 May", "1 May"),
]


def build_payload() -> dict:
    rows = []
    for i, (currency, action, item_name, game_name, amount, acted_on, listed_on) in enumerate(
        TRANSACTIONS
    ):
        row_id = f"history_row_{700000000000000000 + i * 2}_{700000000000000000 + i * 2 + 1}"
        price = f"{currency}{amount}"
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
    out_path = Path(__file__).parent.parent / "tests" / "fixtures" / "drop_lines_history.json"
    out_path.write_text(json.dumps(build_payload(), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(TRANSACTIONS)} transactions to {out_path}")
