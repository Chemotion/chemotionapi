from __future__ import annotations

from chemotion_api.elements.utils import QuantityUnit, GasType, GasCalculations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemotion_api.elements import Sample


def calculate_equivalent_for_gas_product(sample: Sample, ppm: float, temperature_in_k: float) -> None | float:
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
        except ZeroDivisionError or AttributeError:
            return None
    elif role in ['starting_materials', 'reactants']:
        try:
            return mol / ref_mol
        except ZeroDivisionError or AttributeError:
            return None
    return None
