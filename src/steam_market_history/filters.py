from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch

from .models import Transaction


class FilterQueryError(ValueError):
    """Raised when a filter query string can't be parsed."""


_FIELD_ACCESSORS: dict[str, Callable[[Transaction], str]] = {
    "game": lambda t: t.game_name,
    "name": lambda t: t.item_name,
}

# Matches the start of a clause, e.g. "game:" or "!name:", only at the start
# of the query or right after whitespace — so a clause's value can itself
# contain spaces (e.g. `game:Counter-Strike 2 name:*Case` treats
# "Counter-Strike 2" as one value, not two clauses).
_CLAUSE_START_RE = re.compile(
    rf"(?:^|(?<=\s))(!?)({'|'.join(re.escape(f) for f in _FIELD_ACCESSORS)}):"
)


@dataclass(frozen=True, slots=True)
class Clause:
    field: str
    patterns: tuple[str, ...]
    negate: bool = False

    def matches(self, transaction: Transaction) -> bool:
        value = _FIELD_ACCESSORS[self.field](transaction).casefold()
        matched = any(fnmatch(value, pattern.casefold()) for pattern in self.patterns)
        return not matched if self.negate else matched


@dataclass(frozen=True, slots=True)
class Query:
    """An AND of clauses, e.g. `game:CSGO||CS2 name:*Case`.

    Parsed from a string with `parse_query`; matched against a transaction
    with `match_query`. Each clause matches if the transaction's field value
    (case-insensitive) glob-matches any of the clause's `||`-separated
    patterns; a `!field:...` clause negates that.
    """

    clauses: tuple[Clause, ...]

    def matches(self, transaction: Transaction) -> bool:
        return all(clause.matches(transaction) for clause in self.clauses)


def parse_query(text: str) -> Query:
    """Parse a filter query string into a `Query`.

    Syntax: `field:pattern1||pattern2` clauses, ANDed together. `field` is
    one of "game" or "name". A leading `!` on a clause negates it. Patterns
    are shell-style globs (`*`, `?`), matched case-insensitively. A clause's
    value runs up to the next clause (so it may contain spaces, e.g. a full
    game name) — only `||` separates multiple patterns within one clause.
    Example: `game:CSGO||CS2||Counter-Strike 2 name:*Case`.
    """
    stripped = text.strip()
    if not stripped:
        raise FilterQueryError(f"empty filter query: {text!r}")

    starts = list(_CLAUSE_START_RE.finditer(stripped))
    if not starts or starts[0].start() != 0:
        known = ", ".join(sorted(_FIELD_ACCESSORS))
        raise FilterQueryError(
            f"filter query must start with a 'field:' clause (known fields: {known}): {text!r}"
        )

    clauses = []
    for index, start in enumerate(starts):
        negate = start.group(1) == "!"
        field = start.group(2)
        value_end = starts[index + 1].start() if index + 1 < len(starts) else len(stripped)
        raw_value = stripped[start.end() : value_end].strip()

        patterns = tuple(p.strip() for p in raw_value.split("||") if p.strip())
        if not patterns:
            raise FilterQueryError(f"no patterns given for field {field!r} in: {text!r}")

        clauses.append(Clause(field=field, patterns=patterns, negate=negate))

    return Query(tuple(clauses))


def match_query(transaction: Transaction, query: Query) -> bool:
    return query.matches(transaction)


def filter_by_queries(
    transactions: Iterable[Transaction],
    queries: Sequence[Query],
) -> list[Transaction]:
    """Keep transactions matching any of the given queries (OR across queries).

    An empty `queries` sequence matches everything.
    """
    if not queries:
        return list(transactions)
    return [t for t in transactions if any(query.matches(t) for query in queries)]


def unique_game_names(transactions: Iterable[Transaction]) -> list[str]:
    """All distinct game names present, sorted alphabetically.

    Useful for showing available values in a filter UI (CLI or future GUI)
    without the caller needing to know the data ahead of time.
    """
    return sorted({t.game_name for t in transactions})
