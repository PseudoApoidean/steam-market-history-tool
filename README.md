# Steam Market History Tool

## Design principles

- **Core logic is presentation-agnostic.** `parser`, `filters`, and `stats` operate on plain data (a dict in, dataclasses out) with no knowledge of argparse or stdout. `cli.py` is just today's one consumer of that core — a future GUI frontend imports the same package instead of duplicating logic or shelling out to the CLI.
- **No parsing dependencies.** Steam doesn't expose your market history as structured JSON — the useful data is a server-rendered HTML fragment embedded in the export. That fragment's row format is simple and stable enough to extract with the standard library (`re`, `html`), so the tool has zero third-party runtime dependencies and needs no virtualenv for casual use.
- **Currencies are never silently mixed.** Profit is always reported per currency symbol; nothing gets summed across currencies without an explicit (and currently unimplemented) conversion step.
- **Row order over invented dates.** Steam's history omits the year from every date field, even for entries spanning multiple years. Rather than guessing, each transaction keeps `order_index` (its position in Steam's export, newest first) as the only reliable ordering signal.

## Current status / known limitations

- Parses the exact JSON shape produced by Steam's `market/myhistory/render` endpoint (a `results_html` field holding an HTML fragment, plus an `assets` map that isn't currently used). If Steam changes that markup, the row regexes in `parser.py` will need updating.
- No year in per-row dates — see design principles above. Don't rely on `acted_on` / `listed_on` for anything beyond display.
- Multi-currency histories are reported as separate per-currency totals; no FX conversion.
- CLI only for now. GUI is a planned frontend on top of the same `steam_market_history` package (see its `__init__.py` docstring for the intended extension point) — not started yet.

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
steam-market-history path/to/history.json --whitelist "Counter-Strike 2,Rust"
steam-market-history path/to/history.json --blacklist "Team Fortress 2"
steam-market-history path/to/history.json --list-games
```

Or without installing the console script:

```sh
python -m steam_market_history path/to/history.json
```

Keep your actual exported history JSON out of version control — it's personal trade data. `.gitignore` already excludes the sample filename and a `data/` directory if you want somewhere conventional to drop exports.
