from enum import Enum
from typing import Optional


class QuantityUnit(Enum):
    Liter = 'l'
    Mole = 'mol'
    Gram = 'g'
    Equivalent = 'Equivalent'
    Yield = 'Yield'

    @classmethod
    def from_string(cls, input_string: str):
        for unit in list(cls):
            if unit.value.lower() == input_string.lower():
                return unit
        return None



def _get_from_gram(current_value: float, output_unit: QuantityUnit, molecular_weight: Optional[float], purity: float,
                   density: float = 0, molarity: float = 0) -> float:
    if output_unit == QuantityUnit.Gram:
        return current_value
    if output_unit == QuantityUnit.Mole:
        if molecular_weight is None:
            raise KeyError(f'Molecular weight needs to be known!')
        try:
            return current_value * purity / molecular_weight
        except ZeroDivisionError:
            return 0
    if output_unit == QuantityUnit.Liter:
        if molarity != 0:
            return _get_from_gram(current_value, QuantityUnit.Mole, molecular_weight, purity, density, molarity) / molarity
        elif density != 0:
            return current_value / (density * 1000)
    return 0

def _get_from_mol(current_value: float, output_unit: QuantityUnit, molecular_weight: Optional[float], purity: float,
                  density: float = 0, molarity: float = 0) -> float:
    if output_unit == QuantityUnit.Mole:
        return current_value
    if output_unit == QuantityUnit.Gram:
        if molecular_weight is None:
            raise KeyError(f'Molecular weight needs to be known!')
        try:
            return current_value * molecular_weight / purity
        except ZeroDivisionError:
            return 0
    if output_unit == QuantityUnit.Liter:
        if molarity != 0:
            return current_value / molarity
        elif density != 0:
            return _get_from_mol(current_value, QuantityUnit.Gram, molecular_weight, purity, density, molarity) / (density * 1000)

    return 0

def _get_from_liter(current_value: float, output_unit: QuantityUnit, molecular_weight: Optional[float], purity: float,
                     density: float = 0, molarity: float = 0) -> float:
    if output_unit == QuantityUnit.Liter:
        return current_value
    if output_unit == QuantityUnit.Mole:
        if molarity != 0:
            return current_value * molarity
        elif density != 0:
            current_gram = current_value * (density * 1000)
            return _get_from_gram(current_gram, QuantityUnit.Mole, molecular_weight, purity, density, molarity)
    if output_unit == QuantityUnit.Gram:
        if molarity != 0:
            current_gram = current_value * molarity
            return _get_from_mol(current_gram, QuantityUnit.Gram, molecular_weight, 1, density, molarity)
        elif density != 0:
            return current_value * (density * 1000)

        return current_value

    return 0


def calculate_quantity(current_value: float, current_unit: QuantityUnit, output_unit: QuantityUnit,
                       molecular_weight: Optional[float], purity: float, density: float = 0, molarity: float = 0) -> float:
    if current_unit == QuantityUnit.Gram:
        return _get_from_gram(current_value, output_unit, molecular_weight, purity, density, molarity)
    if current_unit == QuantityUnit.Mole:
        return _get_from_mol(current_value, output_unit, molecular_weight, purity, density, molarity)
    if current_unit == QuantityUnit.Liter:
        return _get_from_liter(current_value, output_unit, molecular_weight, purity, density, molarity)
    return 0
