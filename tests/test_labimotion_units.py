"""The unit table in ``options.py`` hand-mirrors LabIMotion's ``units.rb``.

Drift there is invisible to the JSON-Schema validation in ``tests/test_generic_manager.py``
(``test_validate_generic_element`` and friends, which check live klass payloads against the
bundled schemas) because those schemas do not enumerate unit keys. It is equally invisible to the
integration suite unless a seeded klass happens to use a new unit. It surfaces only as a
``ValueError`` when a real klass is loaded, so it is covered here instead.
"""
import logging

import pytest

from chemotion_api.labImotion.items.fields.abstract_fields import (
    SystemDefined,
    _reported_unknown_units,
)
from chemotion_api.labImotion.items.options import UNITS, FieldUnit, get_unit


def test_enum_and_table_cover_the_same_unit_types():
    assert set(FieldUnit) == set(UNITS), 'FieldUnit and UNITS disagree'


@pytest.mark.parametrize(('unit_type', 'unit_key'), [
    # Added by LabIMotion 2.3.0; every one of these used to raise on load.
    ('mass', 'kg'),
    ('energy', 'kWh'),
    ('duration', 'y'),
    ('pressure', 'mpa'),
    ('mass_flow', 'g_min'),
    ('space_time_yield', 'kg_m3_d'),
])
def test_units_added_in_labimotion_23_are_known(unit_type, unit_key):
    field = SystemDefined({'option_layers': unit_type, 'value_system': unit_key})
    assert field.option_layers is FieldUnit(unit_type)
    assert field.value_system == unit_key


def test_unknown_unit_from_the_server_warns_but_still_parses(caplog):
    """A unit added by a *future* LabIMotion must not make the element unreadable."""
    _reported_unknown_units.clear()
    with caplog.at_level(logging.WARNING):
        field = SystemDefined({'option_layers': 'not_a_unit_type', 'value_system': 'not_a_unit'})

    assert field.option_layers == 'not_a_unit_type'   # kept verbatim, not coerced
    assert field.value_system == 'not_a_unit'
    assert 'not_a_unit_type' in caplog.text


def test_unknown_unit_is_reported_once_not_once_per_field():
    _reported_unknown_units.clear()
    for _ in range(5):
        SystemDefined({'option_layers': 'repeated_unknown', 'value_system': 'x'})
    reports = [m for m in _reported_unknown_units if 'repeated_unknown' in m]
    assert len(reports) == 2, reports   # one for the type, one for the key


def test_assignment_from_user_code_is_still_strict():
    """Leniency applies to parsing server payloads, not to typos at the call site."""
    field = SystemDefined({'option_layers': 'mass', 'value_system': 'g'})
    with pytest.raises(ValueError, match='megagram'):
        field.value_system = 'megagram'
    with pytest.raises(ValueError, match='not_a_unit_type'):
        field.option_layers = 'not_a_unit_type'


def test_get_unit_is_total():
    """get_unit must not KeyError on a type the mirror has not learned."""
    assert get_unit('a_type_we_have_never_seen') == []
