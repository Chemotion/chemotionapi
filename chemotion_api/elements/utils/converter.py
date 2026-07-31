"""Unit conversion helpers for physical quantities (time, turnover number and temperature).

Each unit family is an :class:`UnitEnum` subclass that knows how to convert to and from its
canonical default unit. :func:`convert_value` and :func:`convert_value_to_default` provide
family-agnostic conversion entry points.
"""

from enum import Enum
from typing import Self, cast


class UnitEnum(Enum):
    """Base class for unit enumerations that can convert values to and from a default unit."""

    @classmethod
    def from_str(cls, str_in: str) -> Self | None:
        """Resolve a unit member from its string value.

        :param str_in: The string representation of the unit
        :return: The matching member, or ``None`` if the value is not part of this enum
        """
        try:
            return cls(str_in)
        except ValueError:
            return None

    def to_default_unit(self, value: float) -> float:
        """Convert ``value`` (given in this unit) to the family's default unit.

        :param value: The value in this unit
        :return: The value expressed in the default unit
        """
        return 1

    def to_unit(self, value: float, unit: Self) -> float:
        """Convert ``value`` (given in this unit) to another unit of the same family.

        :param value: The value in this unit
        :param unit: The target unit
        :return: The value expressed in ``unit``
        """
        return 1

    @classmethod
    def default_unit(cls) -> Self:
        """:return: The canonical default unit of this family."""
        raise NotImplementedError()


class TIME_UNITS(UnitEnum):
    """Time units (seconds, minutes, hours) with hours as the default unit."""

    SECONDS = 's'
    MINUTES = 'm'
    HOURS = 'h'

    def to_default_unit(self, value: float) -> float:
        """Convert ``value`` from this time unit to hours (the default unit)."""
        if self == TIME_UNITS.SECONDS:
            return value / 3600
        if self == TIME_UNITS.MINUTES:
            return value / 60
        return value

    def to_unit(self, value: float, unit: Self) -> float:
        """Convert ``value`` from this time unit to ``unit``."""
        value = self.to_default_unit(value)
        if unit == TIME_UNITS.SECONDS:
            return value * 3600
        if unit == TIME_UNITS.MINUTES:
            return value * 60
        return value

    @classmethod
    def default_unit(cls) -> Self:
        """:return: The default time unit (hours)."""
        return cls.HOURS


class TON_UNITS(UnitEnum):
    """Turnover number rate units (per second, minute, hour) with per-hour as the default unit."""

    PER_SECOND = 'TON/s'
    PER_MINUTE = 'TON/m'
    PER_HOUR = 'TON/h'

    def to_default_unit(self, value: float) -> float:
        """Convert ``value`` from this turnover number rate unit to per-hour (the default unit)."""
        if self == TON_UNITS.PER_SECOND:
            return value * 3600
        if self == TON_UNITS.PER_MINUTE:
            return value * 60
        return value

    def to_unit(self, value: float, unit: Self) -> float:
        """Convert ``value`` from this turnover number rate unit to ``unit``."""
        value = self.to_default_unit(value)
        if unit == TON_UNITS.PER_SECOND:
            return value / 3600
        if unit == TON_UNITS.PER_MINUTE:
            return value / 60
        return value

    @classmethod
    def default_unit(cls) -> Self:
        """:return: The default turnover number rate unit (per hour)."""
        return cls.PER_HOUR


class TEMPERATURE_UNITS(UnitEnum):
    """Temperature units (Kelvin, Fahrenheit, Celsius) with Kelvin as the default unit."""

    KELVIN = 'K'
    FAHRENHEIT = '°F'
    CELSIUS = '°C'

    def to_default_unit(self, value: float) -> float:
        """Convert ``value`` from this temperature unit to Kelvin (the default unit, as an absolute value)."""
        if self == TEMPERATURE_UNITS.FAHRENHEIT:
            return abs((value - 32) * 5 / 9 + 273.15)
        if self == TEMPERATURE_UNITS.CELSIUS:
            return abs(value + 273.15)
        return abs(value)

    def to_unit(self, value: float, unit: Self) -> float:
        """Convert ``value`` from this temperature unit to ``unit``."""
        value = self.to_default_unit(value)
        if unit == TEMPERATURE_UNITS.FAHRENHEIT:
            return (value - 273.15) * 9 / 5 + 32
        if unit == TEMPERATURE_UNITS.CELSIUS:
            return value - 273.15
        return value

    @classmethod
    def default_unit(cls) -> Self:
        """:return: The default temperature unit (Kelvin)."""
        return cls.KELVIN


def convert_value_to_default(value, unit: str) -> float:
    """Convert ``value`` from ``unit`` to the default unit of its unit family.

    The family is detected automatically from ``unit`` among the known unit enums.

    :param value: The value to convert
    :param unit: The string representation of the source unit
    :return: The value expressed in the family's default unit
    :raises ValueError: If ``unit`` does not belong to any supported unit family
    """
    for enum_class in (TIME_UNITS, TON_UNITS, TEMPERATURE_UNITS):
        if enum_class.from_str(unit) is not None:
            default_unit = enum_class.default_unit().value
            return cast(float, convert_value(value, unit, default_unit))
    raise ValueError(f'The unit {unit} is not supported!')


def convert_value(value: float | None, unit: str, out_unit: str) -> float | None:
    """Convert ``value`` from ``unit`` to ``out_unit`` within the same unit family.

    The unit family is detected automatically from ``unit`` and ``out_unit`` among the known
    unit enums.

    :param value: The value to convert; ``None`` is returned unchanged
    :param unit: The string representation of the source unit
    :param out_unit: The string representation of the target unit
    :return: The converted value, or ``None`` if ``value`` is ``None``
    :raises ValueError: If ``unit`` and ``out_unit`` do not belong to the same supported unit family
    """
    if value is None:
        return value
    if unit == out_unit:
        return value
    for enum_class in (TIME_UNITS, TON_UNITS, TEMPERATURE_UNITS):
        f_unit = enum_class.from_str(unit)
        t_unit = enum_class.from_str(out_unit)
        if f_unit is not None and t_unit is not None:
            return f_unit.to_unit(value, t_unit)  # type: ignore[arg-type]  # f_unit and t_unit are same enum_class at runtime
    raise ValueError(f'The unit {unit} is not supported!')
