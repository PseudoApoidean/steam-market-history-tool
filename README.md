# Steam Market History Tool

## Design principles

- **Core logic is presentation-agnostic.** `parser`, `filters`, and `stats` operate on plain data (a dict in, dataclasses out) with no knowledge of argparse or stdout. `cli.py` is just today's one consumer of that core.
- **The CLI's `--json` output is a stable machine interface, not an afterthought.** A separate GUI project (Steam Market Ledger) shells out to this CLI rather than importing this package directly, so the JSON shape (`{"ok": ..., "totals": ..., "by_game": ..., "series": ..., "acquisition": ...}` / `{"ok": ..., "games": [...]}` / `{"ok": false, "error": ...}`) is treated as a contract: keep it backward compatible, don't casually reshape it.
- **Never present an assumption as a fact.** When the data genuinely doesn't determine an answer (e.g. which specific sales among several are Steam-generated drops), report a real range consistent with the data instead of picking one convention and presenting it as certain. See "Drop detection" below.
- **No parsing dependencies.** Steam doesn't expose your market history as structured JSON — the useful data is a server-rendered HTML fragment embedded in the export. That fragment's row format is simple and stable enough to extract with the standard library (`re`, `html`), so the tool has zero third-party runtime dependencies and needs no virtualenv for casual use.
- **Zero network calls, ever.** This tool only ever reads local files (the history export, an optional `--price-file`). Anything needing live data (e.g. current market prices for unrealized gains) must be fetched elsewhere and handed in as a file — see "Unrealized gains" below.
- **Currencies are never silently mixed.** Profit is always reported per currency symbol; nothing gets summed across currencies without an explicit (and currently unimplemented) conversion step.
- **Row order over invented dates.** Steam's history omits the year from every date field, even for entries spanning multiple years. Rather than guessing, each transaction keeps `order_index` (its position in Steam's export, newest first) as the only reliable ordering signal.

## Current status / known limitations

- Parses the exact JSON shape produced by Steam's `market/myhistory/render` endpoint: a `results_html` field holding an HTML fragment (the primary source), plus `assets`/`hovers` (used to correct `game_name` and populate `category` - see "Game name and category" below). If Steam changes that markup, `parser.py` will need updating. Not every export is guaranteed to have a usable `hovers` linkage for every row - when it's missing, parsing falls back to the HTML-only behavior rather than failing.
- No year in per-row dates — see design principles above. Don't rely on `acted_on` / `listed_on` for anything beyond display.
- Multi-currency histories are reported as separate per-currency totals; no FX conversion.
- No unique per-item/listing identifier. Two visually-identical items (same name, same game) are indistinguishable beyond their name - see "Drop detection" below for what this means for telling real trades apart from Steam-generated drops.
- CLI only, deliberately. The GUI lives in a separate repo (Steam Market Ledger) that adds this repo as a git submodule and drives it as a subprocess via `--json`, rather than importing `steam_market_history` directly.

## Game name and category

Steam's own data conflates "game" and "item type" for anything that isn't a core in-game economy item: every trading card, emoticon, profile background, and booster pack — regardless of which game it's themed after, including a game's own cards — is filed under one generic Steam app (id `753`), the same way Steam's own inventory UI buckets them under a "Steam" tab rather than the tie-in game. This tool corrects `game_name` accordingly: items under that app report `"Steam"` as their game, not a conflated string like `"Don't Starve Together Trading Card"`. Real economy items (a CS2 skin, a Rust weapon skin) keep their own game's name, unaffected.

A `category` field is also captured per transaction (from the same `assets` data, e.g. `"Base Grade Container"`, `"Trading Card"`) and exposed via `--filter`'s `category:` clause and `--json`'s `by_category` key - see below. Not every row resolves one (see "Not every export..." above); a `category`-less transaction just doesn't appear in `by_category` or match any `category:` clause.

Each transaction's real Steam `appid` is also captured (distinct from the display `game_name` - e.g. every community item shares the generic `753`, but a real economy item keeps its own game's appid) and exposed per game via `--json`'s `game_appids` key, e.g. for icon lookups.

## Drop detection

A sold item with no purchase of the same name is presumably a Steam-generated drop (a card/case drop, a gift, anything that entered the account without a market purchase) rather than a real trade — but items are only distinguishable by name (see "No unique per-item/listing identifier" above), so when an item name was sold more times than it was ever purchased, *which* specific sales are drops can't be known, only that some number of them must be. Rather than guessing with a pairing convention (e.g. FIFO) and presenting one £ split as fact — which the data doesn't actually support, since the specific convention chosen changes the £ split, not just a label — each transaction's `acquisition` is one of:

- `drop`: the item was never purchased at all. Confirmed, not a guess.
- `ambiguous`: sold more times than purchased. At least one of these sales must be a drop, but not any specific one - see `--json`'s `acquisition` output for the resulting range.
- `purchased`: every purchase, plus any sale where nothing forces it to be a drop (the default).

## Setup

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Test

```sh
pytest
```

## Usage

```sh
steam-market-history path/to/steamcommunity_market_history.json
steam-market-history path/to/history.json --by-game
steam-market-history path/to/history.json --list-games
```

### Filtering

`--filter` takes a query string and can be repeated (repeats OR together):

- `field:pattern` clauses AND together. A clause's value runs up to the next clause, so it may contain spaces (e.g. a full game name).
- `pattern1||pattern2` within one clause's value OR together.
- Patterns are case-insensitive shell globs (`*`, `?`).
- A leading `!` on a clause negates it.
- Fields: `game` (matches the game name Steam shows - see "Game name and category" above), `name` (matches the item name), `acquisition` (matches `drop`/`ambiguous`/`purchased` - see "Drop detection" above), and `category` (matches Steam's own item-type string, e.g. `"Trading Card"` - a transaction with no resolvable category never matches).
- `any` is a reserved pattern, not a literal value - `field:any` matches every transaction regardless of that field's real value (the same as `field:*`, just a more explicit/self-documenting way to write "no real filter on this field").

```sh
# Lifetime profit from selling CS2/CSGO crates specifically
steam-market-history path/to/history.json --filter "game:CSGO||CS2||Counter-Strike 2 name:*Case"

# Everything except Rust
steam-market-history path/to/history.json --filter "!game:Rust"

# CS2 crates OR anything from Rust
steam-market-history path/to/history.json --filter "game:CS2 name:*Case" --filter "game:Rust"

# Only confirmed Steam-generated drops
steam-market-history path/to/history.json --filter "acquisition:drop"

# Only trading cards
steam-market-history path/to/history.json --filter "category:Trading Card"

# Explicitly no acquisition filter - same result as omitting the field
steam-market-history path/to/history.json --filter "acquisition:any"
```

### Machine-readable output (`--json`)

Add `--json` to any invocation to get structured output instead of text — this is the interface the Steam Market Ledger GUI (and any other script) is expected to use:

```sh
steam-market-history path/to/history.json --json
steam-market-history path/to/history.json --filter "game:CS2 name:*Case" --json
steam-market-history path/to/history.json --list-games --json
```

Always a single JSON object on stdout:

- Success: `{"ok": true, "totals": {...}, "by_game": {...}, "by_item": {...}, "by_category": {...}, "game_appids": {...}, "series": {...}, "acquisition": {...}, "win_rate": {...}, "unrealized": {...}, "unrealized_missing_prices": [...]}` (or `{"ok": true, "games": [...]}` with `--list-games`). `--by-game` has no effect in JSON mode — all of these are always included alongside `totals`.
- Failure (bad `--filter` query, unreadable/malformed history or price file): `{"ok": false, "error": "message"}`.
- No transactions matching the filter is *not* a failure: `{"ok": true, "totals": {}, "by_game": {}, "by_item": {}, "by_category": {}, "game_appids": {}, "series": {}, "acquisition": {}, "win_rate": {}, "unrealized": {}, "unrealized_missing_prices": []}` (exit code is still 1, same as text mode, so shell scripts checking only the exit code keep working — but stdout is always valid JSON regardless of exit code).

`by_item` is the same shape as `by_game` (a currency bucket per key, see below) but keyed by item name instead of game/market - unranked, sort it by whichever currency/field matters for a most/least-profitable view. A drop item's full sale price counts as pure profit here, same as everywhere else - filter to `acquisition:purchased` first (see "Drop detection" above) for a "real trades only" ranking.

`by_category` is keyed by game name, then by category, then the same per-currency shape again - `category` isn't exclusive to any one game (a real game like Counter-Strike 2 can have its own categories, e.g. containers vs. skins, distinct from the community-item "Steam" bucket's Trading Card/Emoticon/etc. split), so category totals stay nested under the game they actually belong to rather than mixed together in one flat bucket. A game with no categorized transactions is simply absent from `by_category`, not present with an empty object.

```json
{"Steam": {"Trading Card": {"£": {"sold_total": "2.50", "sold_count": 1, "purchased_total": "0", "purchased_count": 0, "net_profit": "2.50"}}}}
```

`game_appids` is a flat mapping of game name to that game's real Steam appid (or `null` if never resolved for any of that game's transactions) - a stable identifier distinct from the display game name (which is corrected for the community-item case - see "Game name and category" above), useful for e.g. icon lookups. Icon resolution itself (mapping an appid to a displayed icon) is intentionally left to callers - this tool only ever hands back the id.

```json
{"Steam": "753", "Counter-Strike 2": "730", "Rust": null}
```

`win_rate` is per currency, from FIFO-pairing each item name's purchases to its sales by `order_index` (oldest purchase with oldest sale - a documented convention, not a fact recovered from the data, same reasoning as "Drop detection" above but for a different question: not "was this a drop," but "was this specific paired trade profitable"). Excess sales (drops) and excess purchases (still held) aren't part of any pair and don't count toward this:

```json
{"£": {"profitable_count": 12, "losing_count": 4, "breakeven_count": 1}}
```

Each currency bucket looks like:

```json
{"sold_total": "10.85", "sold_count": 23, "purchased_total": "0", "purchased_count": 0, "net_profit": "10.85"}
```

Amounts are decimal strings (not floats), to avoid floating-point rounding on money.

`series` is a running net-profit total per currency, ordered oldest-transaction-first (using `order_index`, since there's no year to sort by — see design principles above). Each point's `item_name` is the transaction that produced it - the item whose sale/purchase pushed the running total to that value, so a caller can show "what caused this swing" without a separate lookup (this tool's `--json` output never exposes the raw transaction list). Each point also carries three running drop-revenue totals, the same floor/bound/guess distinction as `acquisition` below but accumulated over time instead of a lifetime total:

```json
{"£": [{"order_index": 4, "acted_on": "19 Jun", "item_name": "Kilowatt Case", "cumulative_net_profit": "0.17", "cumulative_confirmed_drop_revenue": "0.17", "cumulative_ambiguous_ceiling": "0.17", "cumulative_best_guess_drop_revenue": "0.17"}, {"order_index": 0, "acted_on": "20 Jun", "item_name": "Operation Bravo Case", "cumulative_net_profit": "1.72", "cumulative_confirmed_drop_revenue": "0.17", "cumulative_ambiguous_ceiling": "1.72", "cumulative_best_guess_drop_revenue": "0.30"}]}
```

`cumulative_confirmed_drop_revenue` is a simple running sum of confirmed-drop sale prices. `cumulative_ambiguous_ceiling` is that plus the running price-sorted max (a real bound, like `ambiguous_drop_revenue_max` below). `cumulative_best_guess_drop_revenue` is that plus a running FIFO guess instead (like `ambiguous_drop_revenue_best_guess` below) — a specific convention, not a bound, so it isn't guaranteed to sit between the confirmed floor and the ambiguous ceiling at every point, only in the lifetime total.

`acquisition` is per currency, giving a confirmed drop-revenue floor, an honest range for what can't be individually resolved, and a single FIFO-convention guess at resolving that range — see "Drop detection" above:

```json
{"£": {"confirmed_drop_revenue": "19.82", "confirmed_drop_count": 24, "ambiguous_drop_revenue_min": "0.23", "ambiguous_drop_revenue_max": "0.41", "ambiguous_drop_revenue_best_guess": "0.30", "ambiguous_count": 4}}
```

`confirmed_drop_revenue`/`confirmed_drop_count` cover sales of items never purchased at all — exact, not an estimate. `ambiguous_drop_revenue_min`/`_max` bound the range of drop revenue possible among sales of items purchased fewer times than sold, where which *specific* sales are drops can't be known; `ambiguous_count` is how many sold transactions fall into that bucket. `ambiguous_drop_revenue_best_guess` resolves that same bucket to one number via a FIFO convention (the oldest purchases pair with the oldest sales by `order_index`, same idea as `win_rate` below but applied to a different question; the most recent, unpaired sales are the guessed drops) — **a documented convention, not a recovered fact**, and independent of the price-sorted min/max above, so it isn't guaranteed to fall between them for every individual item (only in aggregate, generally).

### Unrealized gains (`--price-file`)

This tool never makes network calls, full stop — see design principles above. It has no way to know what a currently-held item is worth right now unless told, so `--price-file PATH` points it at a JSON file of `{"item_name": "current_price", ...}`:

```sh
steam-market-history path/to/history.json --price-file prices.json --json
```

```json
{"Metal Facemask": "4.20", "Ellis' Cap": 12}
```

Prices may be JSON strings or numbers; both are parsed as exact decimals. Fetching a live price, if that ever happens, happens entirely outside this tool (e.g. the Steam Market Ledger GUI making the network call and writing the result to a file in this shape) — this tool can't tell and doesn't need to know whether a price was typed by hand or fetched a second ago.

Without `--price-file`, `unrealized` is `{}` and `unrealized_missing_prices` is `[]` — held items aren't computed at all, not silently zeroed. With it, `unrealized` is per currency:

```json
{"£": {"held_count": 3, "current_value": "12.60", "gain_min": "4.10", "gain_max": "6.85"}}
```

"Held" means purchased more times than sold for that item name — the mirror of drop detection above (that finds excess sales; this finds excess purchases). `current_value` is exact (`held_count` × the supplied price). Which *specific* held units remain unsold can't be known (no unique per-item identifier), so like `acquisition`'s ambiguous bucket, the cost-basis side of the gain is a range, not a guess: `gain_max` assumes the cheapest held-count purchases are the ones still held (minimizing cost basis), `gain_min` assumes the priciest ones are. `unrealized_missing_prices` lists held item names with no entry in `--price-file`, so a caller can show an honest "N held items have no price, this total is partial" instead of silently under-counting.

Or without installing the console script:

```sh
python -m steam_market_history path/to/history.json
```

Keep your actual exported history JSON out of version control — it's personal trade data. `.gitignore` already excludes the sample filename and a `data/` directory if you want somewhere conventional to drop exports.
