"""Offline unit tests for pure-logic helper modules (unit conversion, solvent list,
schema-manager IRIs, LabIMotion conditions, empty-element templates, and the CLI surface)."""
import math
from types import SimpleNamespace

import pytest


# --- elements/utils/converter.py -------------------------------------------------------------

def test_time_unit_conversions():
    from chemotion_api.elements.utils.converter import TIME_UNITS, convert_value

    assert TIME_UNITS.default_unit() is TIME_UNITS.HOURS
    assert TIME_UNITS.SECONDS.to_default_unit(7200) == 2
    assert TIME_UNITS.MINUTES.to_default_unit(90) == 1.5
    assert TIME_UNITS.HOURS.to_default_unit(3) == 3
    assert convert_value(2, 'h', 's') == 7200
    assert convert_value(120, 's', 'm') == 2
    # round-trip
    assert math.isclose(convert_value(convert_value(5.5, 'h', 'm'), 'm', 'h'), 5.5)


def test_ton_unit_conversions():
    from chemotion_api.elements.utils.converter import TON_UNITS, convert_value

    assert TON_UNITS.default_unit() is TON_UNITS.PER_HOUR
    # 1 turnover per second = 3600 per hour
    assert TON_UNITS.PER_SECOND.to_default_unit(1) == 3600
    assert convert_value(3600, 'TON/h', 'TON/s') == 1
    assert convert_value(1, 'TON/m', 'TON/h') == 60


def test_temperature_unit_conversions():
    from chemotion_api.elements.utils.converter import TEMPERATURE_UNITS, convert_value

    assert TEMPERATURE_UNITS.default_unit() is TEMPERATURE_UNITS.KELVIN
    assert TEMPERATURE_UNITS.CELSIUS.to_default_unit(25) == pytest.approx(298.15)
    assert TEMPERATURE_UNITS.FAHRENHEIT.to_default_unit(32) == pytest.approx(273.15)
    assert convert_value(0, '°C', 'K') == pytest.approx(273.15)
    assert convert_value(273.15, 'K', '°F') == pytest.approx(32)
    assert convert_value(100, '°C', '°F') == pytest.approx(212)


def test_convert_value_edge_cases():
    from chemotion_api.elements.utils.converter import (
        TIME_UNITS, convert_value, convert_value_to_default)

    assert convert_value(None, 'h', 's') is None          # None passes through
    assert convert_value(42, 'h', 'h') == 42               # same-unit shortcut
    assert convert_value_to_default(60, 'm') == 1          # family auto-detected → hours
    assert convert_value_to_default(0, '°C') == pytest.approx(273.15)
    assert TIME_UNITS.from_str('not-a-unit') is None
    with pytest.raises(ValueError):
        convert_value(1, 'parsec', 'h')
    with pytest.raises(ValueError):
        convert_value(1, 'h', 'TON/h')                     # families must match
    with pytest.raises(ValueError):
        convert_value_to_default(1, 'parsec')


# --- utils/solvent_manager.py -----------------------------------------------------------------

def test_solvent_list_loads_and_caches():
    from chemotion_api.utils import solvent_manager

    solvents = solvent_manager.get_solvent_list()
    assert 'Acetone' in solvents
    assert isinstance(solvents['Acetone'], dict)
    # cached: the second call returns the very same object
    assert solvent_manager.get_solvent_list() is solvents


# --- schema_manager.py ------------------------------------------------------------------------

def test_schema_manager_parses_version_and_builds_iris():
    from chemotion_api.schema_manager import SchemaManager

    sm = SchemaManager(SimpleNamespace(text="... Version: v3.1.2 ..."))
    assert sm.version == '3.1.2'
    assert sm.generate_model_type('Sample', None) == 'chemotion:type/sample/3.1.2'
    assert sm.generate_model_type('Wrk', '2.0') == 'chemotion:generic_type/wrk/2.0'


def test_schema_manager_falls_back_without_version():
    from chemotion_api.schema_manager import SchemaManager

    sm = SchemaManager(SimpleNamespace(text="no version here"))
    assert sm.version == 'TEST'
    assert sm.generate_model_type('Reaction', None) == 'chemotion:type/reaction/TEST'


# --- labImotion/items/conditions.py -----------------------------------------------------------

def test_condition_is_a_fixed_shape_dict():
    from chemotion_api.labImotion.items.conditions import Condition

    cond = Condition(id='c1', field='f', label='Field', layer='l', value='yes')
    assert cond['field'] == 'f'
    assert set(cond.to_dict().keys()) == {'id', 'field', 'label', 'layer', 'value'}
    # documented PropertyDict semantics: without an on_change callback, writes are dropped
    cond['value'] = 'no'
    assert cond['value'] == 'yes'
    with pytest.raises(KeyError):
        cond['unknown'] = 'x'                  # fixed shape: unknown keys are rejected


# --- elements/empty_elements/__init__.py -------------------------------------------------------

def test_init_container_builds_fresh_root_with_analyses_child():
    from chemotion_api.elements.empty_elements import init_container

    a, b = init_container(), init_container()
    assert a['container_type'] == 'root'
    assert [c['container_type'] for c in a['children']] == ['analyses']
    # fresh UUIDs each call, root and child distinct
    assert a['id'] != a['children'][0]['id']
    assert a['id'] != b['id']


# --- __main__.py (CLI surface) -----------------------------------------------------------------

def test_cli_help_lists_all_commands():
    from click.testing import CliRunner
    from chemotion_api.__main__ import cli

    result = CliRunner().invoke(cli, ['--help'])
    assert result.exit_code == 0
    for command in ('new', 'up', 'stop', 'down', 'backup', 'check', 'change-port'):
        assert command in result.output


@pytest.mark.parametrize('command', ['new', 'up', 'down', 'backup', 'change-port'])
def test_cli_subcommand_help(command):
    from click.testing import CliRunner
    from chemotion_api.__main__ import cli

    result = CliRunner().invoke(cli, [command, '--help'])
    assert result.exit_code == 0
    assert '--help' in result.output
