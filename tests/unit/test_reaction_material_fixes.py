"""Reaction material handling — fixes ported from version-3 (PR #6).

All client-side arithmetic and object wiring, so they carry over from a 3.1.2-targeted branch
unchanged. What is *not* here is the save-time equivalent recompute: it conflicts with this
branch's "serialising must not mutate" invariant. See AI/DEFERRED.md section 2.6.
"""
import pytest

from chemotion_api.elements.utils import GasType, QuantityUnit
from chemotion_api.elements.utils.equivalent import get_equivalent


class _Props(dict):
    pass


class _Sample:
    """Only what get_equivalent touches."""

    def __init__(self, role, reference=False, gas_type=None, coefficient=1.0):
        self.role_in_reaction = role
        self.gas_type = gas_type
        self.properties = _Props(reference=reference, coefficient=coefficient)
        self.reaction = None


def test_a_reference_sample_is_always_one():
    assert get_equivalent(_Sample("starting_materials", reference=True), 1, 2, 0, 0) == 1


@pytest.mark.parametrize("role", ["starting_materials", "reactants"])
def test_a_missing_reference_amount_gives_none_instead_of_typeerror(role):
    """`mol / None` used to escape out of what is effectively a getter and abort a fine save.
    An equivalent that cannot be computed is unknown, not fatal."""
    assert get_equivalent(_Sample(role), 1.0, None, 0, 0) is None


def test_a_zero_reference_amount_still_gives_none():
    assert get_equivalent(_Sample("starting_materials"), 1.0, 0, 0, 0) is None


def test_a_product_with_a_missing_reference_amount_gives_none():
    product = _Sample("products")
    product.reaction = type("_R", (), {"reference_sample": _Sample("starting_materials")})()
    assert get_equivalent(product, 1.0, None, 0, 0) is None


def test_the_plain_molar_ratio_is_still_computed():
    assert get_equivalent(_Sample("reactants"), 3.0, 2.0, 0, 0) == 1.5


# ------------------------------------------------------------------ allowed units for products

class _UnitSample:
    def __init__(self, role, gas_type=None, density=1.0, molarity=0.0):
        self.role_in_reaction = role
        self.gas_type = gas_type
        self.properties = {"density": density, "molarity": {"value": molarity}}

    allowed_quantity_units = property(
        lambda self: __import__("chemotion_api.elements.sample", fromlist=["Sample"])
        .Sample._allowed_quantity_units(self))


def test_a_product_can_be_expressed_in_mol():
    """Products returned `default_set + []`, so mol was unavailable for the one role where a
    chemist is most likely to want it."""
    assert QuantityUnit.Mole in _UnitSample("products").allowed_quantity_units


def test_a_gas_product_still_cannot():
    """Its amount comes from the gas-phase data; offering mol invites a value the server
    recomputes anyway."""
    units = _UnitSample("products", gas_type=GasType.GAS).allowed_quantity_units
    assert QuantityUnit.Mole not in units


def test_a_starting_material_keeps_mol_and_equivalent():
    units = _UnitSample("starting_materials").allowed_quantity_units
    assert QuantityUnit.Mole in units and QuantityUnit.Equivalent in units
