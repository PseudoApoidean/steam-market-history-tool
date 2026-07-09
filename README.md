# Steam Market History Tool

## Design principles

- **Core logic is presentation-agnostic.** `parser`, `filters`, and `stats` operate on plain data (a dict in, dataclasses out) with no knowledge of argparse or stdout. `cli.py` is just today's one consumer of that core.
- **The CLI's `--json` output is a stable machine interface, not an afterthought.** A separate GUI project (Steam Market Ledger) shells out to this CLI rather than importing this package directly, so the JSON shape (`{"ok": ..., "totals": ..., "by_game": ..., "series": ...}` / `{"ok": ..., "games": [...]}` / `{"ok": false, "error": ...}`) is treated as a contract: keep it backward compatible, don't casually reshape it.
- **No parsing dependencies.** Steam doesn't expose your market history as structured JSON — the useful data is a server-rendered HTML fragment embedded in the export. That fragment's row format is simple and stable enough to extract with the standard library (`re`, `html`), so the tool has zero third-party runtime dependencies and needs no virtualenv for casual use.
- **Currencies are never silently mixed.** Profit is always reported per currency symbol; nothing gets summed across currencies without an explicit (and currently unimplemented) conversion step.
- **Row order over invented dates.** Steam's history omits the year from every date field, even for entries spanning multiple years. Rather than guessing, each transaction keeps `order_index` (its position in Steam's export, newest first) as the only reliable ordering signal.

## Current status / known limitations

- Parses the exact JSON shape produced by Steam's `market/myhistory/render` endpoint (a `results_html` field holding an HTML fragment, plus an `assets` map that isn't currently used). If Steam changes that markup, the row regexes in `parser.py` will need updating.
- No year in per-row dates — see design principles above. Don't rely on `acted_on` / `listed_on` for anything beyond display.
- Multi-currency histories are reported as separate per-currency totals; no FX conversion.
- CLI only, deliberately. The GUI lives in a separate repo (Steam Market Ledger) that adds this repo as a git submodule and drives it as a subprocess via `--json`, rather than importing `steam_market_history` directly.

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
- Fields: `game` (matches the game name Steam shows) and `name` (matches the item name).

```sh
# Lifetime profit from selling CS2/CSGO crates specifically
steam-market-history path/to/history.json --filter "game:CSGO||CS2||Counter-Strike 2 name:*Case"

# Everything except Rust
steam-market-history path/to/history.json --filter "!game:Rust"

# CS2 crates OR anything from Rust
steam-market-history path/to/history.json --filter "game:CS2 name:*Case" --filter "game:Rust"
```

### Machine-readable output (`--json`)

Add `--json` to any invocation to get structured output instead of text — this is the interface the Steam Market Ledger GUI (and any other script) is expected to use:

```sh
steam-market-history path/to/history.json --json
steam-market-history path/to/history.json --filter "game:CS2 name:*Case" --json
steam-market-history path/to/history.json --list-games --json
```

Always a single JSON object on stdout:

- Success: `{"ok": true, "totals": {...}, "by_game": {...}, "series": {...}}` (or `{"ok": true, "games": [...]}` with `--list-games`). `--by-game` has no effect in JSON mode — `by_game` and `series` are always included alongside `totals`.
- Failure (bad `--filter` query, unreadable/malformed history file): `{"ok": false, "error": "message"}`.
- No transactions matching the filter is *not* a failure: `{"ok": true, "totals": {}, "by_game": {}, "series": {}}` (exit code is still 1, same as text mode, so shell scripts checking only the exit code keep working — but stdout is always valid JSON regardless of exit code).

Each currency bucket looks like:

```json
{"sold_total": "10.85", "sold_count": 23, "purchased_total": "0", "purchased_count": 0, "net_profit": "10.85"}
```

Amounts are decimal strings (not floats), to avoid floating-point rounding on money.

`series` is a running net-profit total per currency, ordered oldest-transaction-first (using `order_index`, since there's no year to sort by — see design principles above):

```json
{"£": [{"order_index": 4, "acted_on": "19 Jun", "cumulative_net_profit": "0.17"}, {"order_index": 0, "acted_on": "20 Jun", "cumulative_net_profit": "1.72"}]}
```

Or without installing the console script:

```sh
python -m steam_market_history path/to/history.json
```

Keep your actual exported history JSON out of version control — it's personal trade data. `.gitignore` already excludes the sample filename and a `data/` directory if you want somewhere conventional to drop exports.
