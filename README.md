# Steam Market History Tool

## Design principles

- **Core logic is presentation-agnostic.** `parser`, `filters`, and `stats` operate on plain data (a dict in, dataclasses out) with no knowledge of argparse or stdout. `cli.py` is just today's one consumer of that core.
- **The CLI's `--json` output is a stable machine interface, not an afterthought.** A separate GUI project (Steam Market Ledger) shells out to this CLI rather than importing this package directly, so the JSON shape (`{"ok": ..., "totals": ..., "by_game": ..., "series": ..., "acquisition": ...}` / `{"ok": ..., "games": [...]}` / `{"ok": false, "error": ...}`) is treated as a contract: keep it backward compatible, don't casually reshape it.
- **Never present an assumption as a fact.** When the data genuinely doesn't determine an answer (e.g. which specific sales among several are Steam-generated drops), report a real range consistent with the data instead of picking one convention and presenting it as certain. See "Drop detection" below.
- **No parsing dependencies.** Steam doesn't expose your market history as structured JSON — the useful data is a server-rendered HTML fragment embedded in the export. That fragment's row format is simple and stable enough to extract with the standard library (`re`, `html`), so the tool has zero third-party runtime dependencies and needs no virtualenv for casual use.
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

A `category` field is also captured internally per transaction (from the same `assets` data, e.g. `"Base Grade Container"`, `"Trading Card"`) but isn't yet exposed via `--filter` or `--json` — it's not a finished feature yet, just captured now since the correction above already requires looking it up.

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
- Fields: `game` (matches the game name Steam shows - see "Game name and category" above), `name` (matches the item name), and `acquisition` (matches `drop`/`ambiguous`/`purchased` - see "Drop detection" above).

```sh
# Lifetime profit from selling CS2/CSGO crates specifically
steam-market-history path/to/history.json --filter "game:CSGO||CS2||Counter-Strike 2 name:*Case"

# Everything except Rust
steam-market-history path/to/history.json --filter "!game:Rust"

# CS2 crates OR anything from Rust
steam-market-history path/to/history.json --filter "game:CS2 name:*Case" --filter "game:Rust"

# Only confirmed Steam-generated drops
steam-market-history path/to/history.json --filter "acquisition:drop"
```

### Machine-readable output (`--json`)

Add `--json` to any invocation to get structured output instead of text — this is the interface the Steam Market Ledger GUI (and any other script) is expected to use:

```sh
steam-market-history path/to/history.json --json
steam-market-history path/to/history.json --filter "game:CS2 name:*Case" --json
steam-market-history path/to/history.json --list-games --json
```

Always a single JSON object on stdout:

- Success: `{"ok": true, "totals": {...}, "by_game": {...}, "by_item": {...}, "series": {...}, "acquisition": {...}}` (or `{"ok": true, "games": [...]}` with `--list-games`). `--by-game` has no effect in JSON mode — `by_game`, `by_item`, `series`, and `acquisition` are always included alongside `totals`.
- Failure (bad `--filter` query, unreadable/malformed history file): `{"ok": false, "error": "message"}`.
- No transactions matching the filter is *not* a failure: `{"ok": true, "totals": {}, "by_game": {}, "by_item": {}, "series": {}, "acquisition": {}}` (exit code is still 1, same as text mode, so shell scripts checking only the exit code keep working — but stdout is always valid JSON regardless of exit code).

`by_item` is the same shape as `by_game` (a currency bucket per key, see below) but keyed by item name instead of game/market - unranked, sort it by whichever currency/field matters for a most/least-profitable view. A drop item's full sale price counts as pure profit here, same as everywhere else - filter to `acquisition:purchased` first (see "Drop detection" above) for a "real trades only" ranking.

Each currency bucket looks like:

```json
{"sold_total": "10.85", "sold_count": 23, "purchased_total": "0", "purchased_count": 0, "net_profit": "10.85"}
```

Amounts are decimal strings (not floats), to avoid floating-point rounding on money.

`series` is a running net-profit total per currency, ordered oldest-transaction-first (using `order_index`, since there's no year to sort by — see design principles above):

```json
{"£": [{"order_index": 4, "acted_on": "19 Jun", "cumulative_net_profit": "0.17"}, {"order_index": 0, "acted_on": "20 Jun", "cumulative_net_profit": "1.72"}]}
```

`acquisition` is per currency, giving a confirmed drop-revenue floor plus an honest range for what can't be individually resolved — see "Drop detection" above:

```json
{"£": {"confirmed_drop_revenue": "19.82", "confirmed_drop_count": 24, "ambiguous_drop_revenue_min": "0.23", "ambiguous_drop_revenue_max": "0.41", "ambiguous_count": 4}}
```

`confirmed_drop_revenue`/`confirmed_drop_count` cover sales of items never purchased at all — exact, not an estimate. `ambiguous_drop_revenue_min`/`_max` bound the range of drop revenue possible among sales of items purchased fewer times than sold, where which *specific* sales are drops can't be known; `ambiguous_count` is how many sold transactions fall into that bucket.

Or without installing the console script:

```sh
python -m steam_market_history path/to/history.json
```

Keep your actual exported history JSON out of version control — it's personal trade data. `.gitignore` already excludes the sample filename and a `data/` directory if you want somewhere conventional to drop exports.
