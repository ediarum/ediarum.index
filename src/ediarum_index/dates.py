"""Uncertain historical dates: parse messy strings to a single integer sort key.

Register date fields are stored and exported **verbatim** (``"nach 1824"``,
``"um 1810"``, ``"3. Jh."``, ``"381-407"``). To still order a register by date,
the write path (``services.create_entry`` / ``services.update_entry``) calls
``sorts_for`` and stores the result in the indexed ``entry.birth_sort`` /
``entry.death_sort`` columns. Nothing here is shown to the user.

Parsing is best-effort and lenient: anything we cannot make sense of yields
``None`` (the row then sorts last). A parsed value is reduced to
``year * 10000 + month * 100 + day`` — a plain int that orders correctly across
BCE (negative years) and partially-known dates (missing month/day default to 1).
"""

from __future__ import annotations

import re

# (lower, upper) sort keys — equal for a point date, distinct for a range/period.
_Span = tuple[int, int]

_YEAR = r"-?\d{1,4}"
_YEAR_RE = re.compile(_YEAR)
_BCE_RE = re.compile(r"\bv\.?\s?chr\.?", re.IGNORECASE)
_CENTURY_RE = re.compile(r"(\d{1,2})\s*\.\s*jh", re.IGNORECASE)
# a year range: "1810-1815", "1810/1815", "1810–1815", "216–276/77"
_RANGE_RE = re.compile(rf"({_YEAR})\s*[-–/]\s*(\d{{1,4}})")

# "nach 1824", "vor 1824", "um 1810", "ca. 1810", … — the qualifier doesn't move
# the sort anchor, so these just fall through to the plain-year branch.


def _key(year: int, month: int = 1, day: int = 1) -> int:
    """``year*10000 + month*100 + day`` — monotonic and BCE-safe."""
    return year * 10_000 + month * 100 + day


def parse_date(raw: object) -> _Span | None:
    """A single (possibly uncertain) date string -> ``(lower, upper)`` sort keys.

    ``nach`` / ``vor`` / ``um`` / ``ca.`` anchor on the year they name; ``N. Jh.``
    becomes the century's span; ``YYYY-YYYY`` a range; ``… v. Chr.`` flips to BCE.
    Placeholder-only values (``*``, ``†``, ``?``, ``""``) -> ``None``.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or not any(c.isdigit() for c in text):
        return None

    bce = bool(_BCE_RE.search(text))

    def y(n: int) -> int:
        return -n if bce and n > 0 else n

    m = _CENTURY_RE.search(text)
    if m:
        c = int(m.group(1))
        lo, hi = (c - 1) * 100 + 1, c * 100
        if bce:
            lo, hi = -hi, -lo
        return _key(lo), _key(hi)

    m = _RANGE_RE.search(text)
    if m:
        lo, hi = sorted((y(int(m.group(1))), y(int(m.group(2)))))
        return _key(lo), _key(hi)

    token = _YEAR_RE.search(text)
    if token is None:
        return None
    k = _key(y(int(token.group())))
    return k, k  # nach / vor / um / ca. all anchor on the stated year


def parse_floruit(text: object) -> _Span | None:
    """A ``<floruit>`` value (pta) — a fuzzy active period. Same machinery as
    ``parse_date``, whose range / century / BCE handling already covers it."""
    return parse_date(text)


def sort_key(span: _Span | None) -> int | None:
    """Lower bound of a parsed span."""
    return None if span is None else span[0]


def sort_key_upper(span: _Span | None) -> int | None:
    """Upper bound of a parsed span (the end of a ``<floruit>`` period)."""
    return None if span is None else span[1]


def sorts_for(data: dict) -> dict[str, int | None]:
    """``{"birth_sort": …, "death_sort": …}`` for one entry's ``data``.

    Persons dated by ``birth_date`` / ``death_date`` (Leibniz, mop) map straight
    through. Persons dated only by ``floruit`` (pta) get the period's start as
    ``birth_sort`` and its end as ``death_sort``, so either sort key orders them
    sensibly next to dated persons.
    """
    birth = data.get("birth_date")
    death = data.get("death_date")
    floruit = data.get("floruit")
    if birth is None and death is None and floruit:
        period = parse_floruit(floruit)
        return {"birth_sort": sort_key(period), "death_sort": sort_key_upper(period)}
    return {
        "birth_sort": sort_key(parse_date(birth)),
        "death_sort": sort_key(parse_date(death)),
    }
