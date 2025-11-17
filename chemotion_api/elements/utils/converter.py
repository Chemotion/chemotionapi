import math
from enum import Enum
from typing import Optional, Self


class UnitEnum(Enum):
    @classmethod
    def from_str(cls, str_in: str) -> Self | None:
        try:
            return cls(str_in)
        except ValueError:
            return None

    def to_default_unit(self, value: float) -> float:
        return 1

    def to_unit(self, value: float, unit: Self) -> float:
        return 1

    @classmethod
    def default_unit(cls) -> Self:
        raise NotImplementedError()


class TIME_UNITS(UnitEnum):
    SECONDS = 's'
    MINUTES = 'm'
    HOURS = 'h'

    def to_default_unit(self, value: float) -> float:
        if self == TIME_UNITS.SECONDS:
            return value / 3600
        if self == TIME_UNITS.MINUTES:
            return value / 60
        return value

    def to_unit(self, value: float, unit: Self) -> float:
        value = self.to_default_unit(value)
        if unit == TIME_UNITS.SECONDS:
            return value * 3600
        if unit == TIME_UNITS.MINUTES:
            return value * 60
        return value

    @classmethod
    def default_unit(cls) -> Self:
        return cls.HOURS


class TON_UNITS(UnitEnum):
    PER_SECOND = 'TON/s'
    PER_MINUTE = 'TON/m'
    PER_HOUR = 'TON/h'

    def to_default_unit(self, value: float) -> float:
        if self == TON_UNITS.PER_SECOND:
            return value * 3600
        if self == TON_UNITS.PER_MINUTE:
            return value * 60
        return value

    def to_unit(self, value: float, unit: Self) -> float:
        value = self.to_default_unit(value)
        if unit == TON_UNITS.PER_SECOND:
            return value / 3600
        if unit == TON_UNITS.PER_MINUTE:
            return value / 60
        return value

    @classmethod
    def default_unit(cls) -> Self:
        return cls.PER_HOUR


class TEMPERATURE_UNITS(UnitEnum):
    KELVIN = 'K'
    FAHRENHEIT = '°F'
    CELSIUS = '°C'

    def to_default_unit(self, value: float) -> float:
        if self == TEMPERATURE_UNITS.FAHRENHEIT:
            return abs((value - 32) * 5 / 9 + 273.15)
        if self == TEMPERATURE_UNITS.CELSIUS:
            return abs(value + 273.15)
        return abs(value)

    def to_unit(self, value: float, unit: Self) -> float:
        value = self.to_default_unit(value)
        if unit == TEMPERATURE_UNITS.FAHRENHEIT:
            return (value - 273.15) * 9 / 5 + 32
        if unit == TEMPERATURE_UNITS.CELSIUS:
            return value - 273.15
        return value

    @classmethod
    def default_unit(cls) -> Self:
        return cls.KELVIN


def convert_value_to_default(value, unit: str) -> float:
    for enum_class in (TIME_UNITS, TON_UNITS, TEMPERATURE_UNITS):
        if enum_class.from_str(unit) is not None:
            default_unit = enum_class.default_unit().value
            return convert_value(value, unit, default_unit)
    raise ValueError(f'The unit {unit} is not supported!')


def convert_value(value: Optional[float], unit: str, out_unit: str) -> float | None:
    if value is None:
        return value
    if unit == out_unit:
        return value
    for enum_class in (TIME_UNITS, TON_UNITS, TEMPERATURE_UNITS):
        f_unit = enum_class.from_str(unit)
        t_unit = enum_class.from_str(out_unit)
        if f_unit is not None and t_unit is not None:
            return f_unit.to_unit(value, t_unit)
    raise ValueError(f'The unit {unit} is not supported!')
