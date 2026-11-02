"""Quantity conversion utilities for samples (mass / amount-of-substance / volume) and gases.

Provides the :class:`QuantityUnit` and :class:`GasType` enumerations together with
:func:`calculate_quantity`, which converts a value between gram, mole and liter taking molecular
weight, purity, density and molarity into account, and :class:`GasCalculations` for gas-phase
(feedstock / catalyst / gas) conversions.
"""

from enum import Enum
from typing import Optional


class GasType(Enum):
    """Role a gas-phase material plays in a reaction (``off``/``gas``/``catalyst``/``feedstock``)."""

    OFF = 'off'
    GAS = 'gas'
    CATALYST = 'catalyst'
    FEEDSTOCK = 'feedstock'


class QuantityUnit(Enum):
    """A unit a sample quantity can be expressed in (liter, mole, gram, equivalent or yield)."""

    Liter = 'l'
    Mole = 'mol'
    Gram = 'g'
    Equivalent = 'Equivalent'
    Yield = 'Yield'

    @classmethod
    def from_string(cls, input_string: str):
        """Resolve a unit from its string value, case-insensitively.

        :param input_string: The textual unit (e.g. ``'mol'``, ``'G'``)
        :return: The matching :class:`QuantityUnit`, or ``None`` if none matches
        """
        if not isinstance(input_string, str):
            return None
        for unit in list(cls):
            if unit.value.lower() == input_string.lower():
                return unit
        return None


def _get_from_gram(current_value: float, output_unit: QuantityUnit, molecular_weight: float | None, purity: float,
                   density: float = 0, molarity: float = 0) -> float:
    if output_unit == QuantityUnit.Gram:
        return current_value
    if output_unit == QuantityUnit.Mole:
        if molecular_weight is None:
            raise KeyError(f'Molecular weight needs to be known!')
        try:
            return current_value * purity / molecular_weight
        except ZeroDivisionError:
            return float('NaN')
    if output_unit == QuantityUnit.Liter:
        if molarity != 0:
            return _get_from_gram(current_value, QuantityUnit.Mole, molecular_weight, purity, density,
                                  molarity) / molarity
        elif density != 0:
            return current_value / (density * 1000)

    return float('NaN')


def _get_from_mol(current_value: float, output_unit: QuantityUnit, molecular_weight: float | None, purity: float,
                  density: float = 0, molarity: float = 0) -> float:
    if output_unit == QuantityUnit.Mole:
        return current_value
    if output_unit == QuantityUnit.Gram:
        if molecular_weight is None:
            raise KeyError(f'Molecular weight needs to be known!')
        try:
            return current_value * molecular_weight / purity
        except ZeroDivisionError:
            return float('NaN')
    if output_unit == QuantityUnit.Liter:
        if molarity != 0:
            return current_value / molarity
        elif density != 0:
            return _get_from_mol(current_value, QuantityUnit.Gram, molecular_weight, purity, density, molarity) / (
                        density * 1000)

    return float('NaN')


def _get_from_liter(current_value: float, output_unit: QuantityUnit, molecular_weight: float | None, purity: float,
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

    return float('NaN')


def calculate_quantity(current_value: float, current_unit: QuantityUnit, output_unit: QuantityUnit,
                       molecular_weight: float | None, purity: float, density: float = 0, molarity: float = 0,
                       gas_type: GasType = GasType.OFF, vessel_size: float = 0, temperature_in_k: float = 0, ppm: float = 0, time_in_h: float = 0) -> float:
    """Convert a sample quantity from one unit to another.

    For ordinary (non-gas) materials the value is converted between gram, mole and liter using the
    molecular weight, purity, density and molarity. If ``gas_type`` is not :attr:`GasType.OFF` the
    conversion is delegated to :meth:`GasCalculations.calculate_quantity`.

    :param current_value: The value to convert
    :param current_unit: The unit ``current_value`` is given in
    :param output_unit: The desired output unit
    :param molecular_weight: Molecular weight; required for gram/mole conversions
    :param purity: Purity factor of the material
    :param density: Density (used for liter conversions); 0 if unknown
    :param molarity: Molarity (used for liter conversions); 0 if unknown
    :param gas_type: Gas role; non-OFF triggers the gas-phase calculation path
    :param vessel_size: Vessel size used for gas conversions
    :param temperature_in_k: Temperature in Kelvin used for gas conversions
    :param ppm: Parts-per-million used for gas conversions
    :param time_in_h: Time in hours used for gas conversions
    :return: The converted value, or ``NaN`` if the conversion is not possible
    """
    if gas_type != GasType.OFF:
        return GasCalculations.calculate_quantity(current_value, current_unit, output_unit, molecular_weight, purity, density,
                                           molarity, gas_type, vessel_size, temperature_in_k, ppm, time_in_h)
    if current_unit == QuantityUnit.Gram:
        return _get_from_gram(current_value, output_unit, molecular_weight, purity, density, molarity)
    if current_unit == QuantityUnit.Mole:
        return _get_from_mol(current_value, output_unit, molecular_weight, purity, density, molarity)
    if current_unit == QuantityUnit.Liter:
        return _get_from_liter(current_value, output_unit, molecular_weight, purity, density, molarity)
    return float('NaN')


class GasCalculations:
    """Quantity conversions for gas-phase materials (feedstock, catalyst and gas)."""

    @classmethod
    def calculate_quantity(cls, current_value: float, current_unit: QuantityUnit, output_unit: QuantityUnit,
                           molecular_weight: float | None, purity: float, density: float = 0, molarity: float = 0,
                           gas_type: GasType = GasType.OFF, vessel_size: float = 0, temperature_in_k: float = 0, ppm: float = 0, time_in_h: float = 0) -> float:
        """Convert a quantity for a gas-phase material depending on its :class:`GasType`.

        A catalyst is treated like an ordinary material; feedstock is converted between mole and
        liter using the ideal gas law; a gas is converted via concentration (ppm) and vessel size.

        :param current_value: The value to convert
        :param current_unit: The unit ``current_value`` is given in
        :param output_unit: The desired output unit
        :param molecular_weight: Molecular weight of the material
        :param purity: Purity factor of the material
        :param density: Density of the material; 0 if unknown
        :param molarity: Molarity of the material; 0 if unknown
        :param gas_type: The gas role driving the calculation
        :param vessel_size: Vessel size used for gas conversions
        :param temperature_in_k: Temperature in Kelvin used for gas conversions
        :param ppm: Parts-per-million concentration used for gas conversions
        :param time_in_h: Time in hours used for gas conversions
        :return: The converted value, or ``NaN`` if the conversion is not possible
        """
        if gas_type == GasType.CATALYST:
            # Catalyst is calculated as normal material
            return calculate_quantity(current_value, current_unit, output_unit, molecular_weight, purity, density,
                                           molarity, GasType.OFF)
        if gas_type == GasType.FEEDSTOCK:
            if current_unit == QuantityUnit.Mole:
                return cls._feedstock_from_mol(current_value, output_unit, purity)
            if current_unit == QuantityUnit.Liter:
                return cls._feedstock_from_liter(current_value, output_unit, purity)
        if gas_type == GasType.GAS:
            return cls._gas_converter(output_unit, molecular_weight, vessel_size, temperature_in_k, ppm, time_in_h )
        return float('NaN')


    IDEAL_GAS_CONSTANT = 0.0821
    PARTS_PER_MILLION_FACTOR = 1_000_000
    DEFAULT_TEMPERATURE_IN_KELVIN = 294

    @classmethod
    def _feedstock_from_liter(cls, current_value, output_unit, purity):
        if output_unit == QuantityUnit.Liter:
            return current_value
        if output_unit == QuantityUnit.Mole:
            return (current_value * purity) / (cls.IDEAL_GAS_CONSTANT * cls.DEFAULT_TEMPERATURE_IN_KELVIN)
        return float('NaN')

    @classmethod
    def _feedstock_from_mol(cls, current_value, output_unit, purity):
        if output_unit == QuantityUnit.Mole:
            return current_value
        if output_unit == QuantityUnit.Liter:
            return  (cls.IDEAL_GAS_CONSTANT * cls.DEFAULT_TEMPERATURE_IN_KELVIN) / (current_value * purity)
        return float('NaN')

    @classmethod
    def _gas_converter(cls, output_unit, molecular_weight, vessel_size,  temperature_in_k: float = 0, ppm: float = 0, time_in_h: float = 0):
        if output_unit == QuantityUnit.Liter:
            return vessel_size / molecular_weight
        if output_unit == QuantityUnit.Mole:
            if ppm is None or temperature_in_k is None:
                return 0
            return (ppm * vessel_size) / (cls.IDEAL_GAS_CONSTANT * temperature_in_k * cls.PARTS_PER_MILLION_FACTOR)
        return float('NaN')