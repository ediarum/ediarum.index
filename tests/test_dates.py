"""dates.py: parsing uncertain date strings to a monotonic integer sort key."""

import pytest

from ediarum_index.dates import parse_date, sort_key, sorts_for


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "*", "†", "?", "u. J.", None],
)
def test_no_digits_is_none(raw):
    assert parse_date(raw) is None
    assert sort_key(parse_date(raw)) is None


def test_plain_years_are_monotonic():
    keys = [sort_key(parse_date(s)) for s in ["1700", "1750", "1799", "1801"]]
    assert keys == sorted(keys)
    assert len(set(keys)) == 4


def test_qualifier_only_anchors_the_year_it_names():
    # "nach 1750" / "um 1750" / "vor 1750" all key off 1750 — the qualifier is
    # kept verbatim in the stored string, it just doesn't move the sort anchor
    for s in ("1750", "nach 1750", "um 1750", "ca. 1750", "vor 1750"):
        assert sort_key(parse_date(s)) // 10_000 == 1750


def test_ranges_centuries_and_bce():
    # a range anchors on its lower bound
    assert sort_key(parse_date("1810-1815")) // 10_000 == 1810
    # "3. Jh." -> the 3rd century starts in year 201
    assert sort_key(parse_date("3. Jh.")) // 10_000 == 201
    # BCE years are negative, so older sorts first
    bce = sort_key(parse_date("356-323 v.Chr."))
    ce = sort_key(parse_date("14"))
    assert bce < 0 < ce
    assert sort_key(parse_date("400 v.Chr.")) < sort_key(parse_date("356 v.Chr."))


def test_sorts_for_reads_birth_and_death_fields():
    out = sorts_for({"birth_date": "nach 1824", "death_date": "1888"})
    assert out["birth_sort"] // 10_000 == 1824
    assert out["death_sort"] // 10_000 == 1888


def test_sorts_for_falls_back_to_floruit():
    out = sorts_for({"floruit": "381-407"})
    assert out["birth_sort"] // 10_000 == 381  # period start
    assert out["death_sort"] // 10_000 == 407  # period end


def test_sorts_for_empty_is_all_none():
    assert sorts_for({}) == {"birth_sort": None, "death_sort": None}
    assert sorts_for({"birth_date": "?"}) == {"birth_sort": None, "death_sort": None}
