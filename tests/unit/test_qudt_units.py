"""Unit strings become QUDT IRIs, or nothing — never a guess."""
import pytest

from chemotion_api.elements.utils.qudt import QUDT_UNIT, _BY_SPELLING, qudt_unit


@pytest.mark.parametrize("unit,expected", [
    ("g", "GM"), ("mg", "MilliGM"), ("µg", "MicroGM"), ("kg", "KiloGM"),
    ("mol", "MOL"), ("mmol", "MilliMOL"), ("µmol", "MicroMOL"),
    ("l", "L"), ("ml", "MilliL"), ("µl", "MicroL"),
    ("M", "MOL-PER-L"), ("mol/l", "MOL-PER-L"),
    ("°C", "DEG_C"), ("K", "K"),
    ("h", "HR"), ("s", "SEC"), ("min", "MIN"), ("%", "PERCENT"),
])
def test_known_units_map(unit, expected):
    assert qudt_unit(unit) == QUDT_UNIT + expected


@pytest.mark.parametrize("unit", ["°F", "F", "deg_F", "Fahrenheit"])
def test_fahrenheit_maps_to_deg_f(unit):
    """Regression, two bugs in one.

    `Reaction.temperature` documents `valueUnit` as one of '°C', '°F' or 'K', but °F had no
    mapping: it produced `.../°F`, which does not resolve. Bare `F` was worse — it resolves,
    to QUDT's **Faraday**, a unit of electric charge. A wrong-but-resolving identifier cannot
    be detected downstream.
    """
    assert qudt_unit(unit) == QUDT_UNIT + "DEG_F"


@pytest.mark.parametrize("unit", ["bar", "cm", "angstrom", "atm", "rpm", "ah_g", "nonsense"])
def test_unknown_units_yield_nothing_rather_than_a_guess(unit):
    """The old fallback appended the raw string. QUDT spells these BAR, CentiM, ANGSTROM —
    so an appended name is dead except by accident, and callers must omit `unit` instead."""
    assert qudt_unit(unit) is None


def test_absent_unit_is_unitless():
    for empty in (None, "", "   "):
        assert qudt_unit(empty) == QUDT_UNIT + "UNITLESS"


def test_matching_is_case_and_space_insensitive():
    assert qudt_unit("  Mg ") == qudt_unit("mg")
    assert qudt_unit("HOUR") == qudt_unit("h")


def test_no_mapping_target_is_obviously_malformed():
    """Cheap guard on the table itself: QUDT local names carry no spaces, slashes or
    non-ASCII. It will not catch a wrong-but-plausible name — the live check does that."""
    for spelling, iri in _BY_SPELLING.items():
        local = iri[len(QUDT_UNIT):]
        assert local and local.isascii(), f"{spelling!r} -> {iri}"
        assert not set(local) & set(" /°"), f"{spelling!r} -> {iri}"
