"""Equivalent / stoichiometry calculations for the samples of a reaction."""
from __future__ import annotations

from chemotion_api.elements.utils import GasType, GasCalculations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemotion_api.elements import Sample


def calculate_equivalent_for_gas_product(sample: Sample, ppm: float, temperature_in_k: float) -> None | float:
    """Calculate the equivalent of a gaseous product sample relative to the reaction's feedstock.

    :param sample: The gas product sample whose equivalent is computed
    :param ppm: The measured concentration of the gas in parts per million
    :param temperature_in_k: The temperature of the measurement in Kelvin
    :return: The calculated equivalent, or ``None`` if no feedstock or vessel size is available,
        or the purity/temperature data is missing
    """
    reaction = sample.reaction

    ref_material = reaction.get_feedstock()
    if ref_material is None or not sample.vessel_size:
        return None
    f_purity = ref_material.properties['purity']
    try:
        return ppm * GasCalculations.DEFAULT_TEMPERATURE_IN_KELVIN / (
                f_purity * temperature_in_k * GasCalculations.PARTS_PER_MILLION_FACTOR)
    except TypeError:
        return None


def get_equivalent(sample: Sample, mol: float, ref_mol: float, ppm: float, temperature_in_k: float):
    """Compute the stoichiometric equivalent of ``sample`` relative to the reaction reference.

    The reference sample always has an equivalent of ``1``. Products are scaled by their
    stoichiometry coefficient (or computed via :func:`calculate_equivalent_for_gas_product` for
    gaseous products), while starting materials and reactants use the plain molar ratio.

    :param sample: The sample whose equivalent is computed
    :param mol: The amount of substance of ``sample`` in mol
    :param ref_mol: The amount of substance of the reference sample in mol
    :param ppm: The gas concentration in parts per million (used only for gaseous products)
    :param temperature_in_k: The temperature in Kelvin (used only for gaseous products)
    :return: The calculated equivalent, or ``None`` if it cannot be determined
    """
    role = sample.role_in_reaction
    if sample.properties['reference']:
        return 1
    if role == 'products':
        if sample.gas_type == GasType.GAS:
            return calculate_equivalent_for_gas_product(sample, ppm, temperature_in_k)

        try:
            stoichiometry_coefficient = (sample.properties['coefficient'] or 1.0) / (
                        sample.reaction.reference_sample.properties['coefficient'] or 1.0)
            return mol / ref_mol / stoichiometry_coefficient
        except (ZeroDivisionError, AttributeError):
            return None
    elif role in ['starting_materials', 'reactants']:
        try:
            return mol / ref_mol
        except (ZeroDivisionError, AttributeError):
            return None
    return None
