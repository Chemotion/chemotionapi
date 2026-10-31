"""An unknown solvent name should say what you probably meant.

Ported from Martin's version-3 branch (PR #6). Pure client logic — a lookup in a bundled JSON
table — so nothing here depends on the ELN version, which is why it ports unchanged from a branch
written against 3.1.2.

The old message named the key but offered nothing else, and the table has several hundred entries
with names like "Tetrahydrofuran (THF)" that nobody guesses on the first try.
"""
import pytest

from chemotion_api.utils.solvent_manager import get_solvent_info, get_solvent_list


def test_a_known_solvent_returns_its_entry():
    name = next(iter(get_solvent_list()))
    assert get_solvent_info(name) == get_solvent_list()[name]


def test_an_unknown_name_raises_with_the_discovery_hint():
    with pytest.raises(KeyError, match="get_solvent_list"):
        get_solvent_info("Definitely Not A Solvent 12345")


def test_a_substring_match_is_suggested():
    """"THF" should find "Tetrahydrofuran (THF)" — the parenthesised form is unguessable."""
    names = [n for n in get_solvent_list() if "THF" in n]
    if not names:
        pytest.skip("bundled solvent table has no THF entry")
    with pytest.raises(KeyError) as excinfo:
        get_solvent_info("THF")
    assert "Did you mean" in str(excinfo.value)


def test_a_near_miss_is_suggested():
    """A typo should still land, via difflib rather than substring."""
    name = next(iter(get_solvent_list()))
    typo = name[:-1] + "x" if len(name) > 3 else name + "x"
    with pytest.raises(KeyError) as excinfo:
        get_solvent_info(typo)
    assert "Did you mean" in str(excinfo.value) or "not available" in str(excinfo.value)
