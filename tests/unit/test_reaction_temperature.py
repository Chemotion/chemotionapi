import pytest
from jsonschema import validate, ValidationError

from chemotion_api.elements.reaction import Temperature
from chemotion_api.elements.schemas.reaction import schema


def _validate(temperature: Temperature):
    validate({'temperature': temperature}, {'type': 'object', 'properties': {'temperature': schema['properties']['temperature']}})


@pytest.mark.parametrize('value', [100, 0, -78, -78.5, 25.0])
def test_temperature_values_are_valid(value):
    temperature = Temperature()
    temperature.add_time_point(0, 30, 0, value)
    _validate(temperature)


@pytest.mark.parametrize('value', ['abc', '-', '1-2', '--5', ''])
def test_invalid_temperature_values(value):
    with pytest.raises(ValidationError):
        _validate(Temperature(data=[{'time': '00:00:00', 'value': value}]))
