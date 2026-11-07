"""Screens (M1.1), offline, against a real ELN `main` screen payload (one wellplate, one plan)."""
import copy
import json
import os

import pytest

from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.elements.screen import Screen
from chemotion_api.elements.wellplate import Wellplate
from chemotion_api.schema_manager import SchemaManager

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'screen_v4_main.json')


class _About:
    status_code, text = 200, '<h4>Version: v4.0.0</h4>'


class _Session:
    schema_manager = SchemaManager(_About())
    _host_url = 'http://eln.test'


class _Segments:
    all_classes = []


def _screen(payload=None):
    if payload is None:
        with open(FIXTURE) as f:
            payload = json.load(f)
    return Screen(_Segments(), _Session(), json_data=payload)


def _linked(cls, elem_id):
    element = cls.__new__(cls)
    element._id = elem_id
    return element


def test_a_server_screen_parses_into_properties_and_linked_elements():
    screen = _screen()
    assert screen.properties['name'] == 'Fixture screen'
    assert screen.properties['collaborator'] == 'Max Mustermann'
    assert [type(w) for w in screen.wellplates] == [Wellplate]
    assert [type(r) for r in screen.research_plans] == [ResearchPlan]


def test_links_are_saved_as_id_lists_and_the_nested_records_are_not_sent():
    screen = _screen()
    data = screen.clean_data()
    assert data['wellplate_ids'] == [w.id for w in screen.wellplates]
    assert data['research_plan_ids'] == [r.id for r in screen.research_plans]
    assert 'wellplates' not in data and 'research_plans' not in data
    assert 'container' in data


def test_serialising_does_not_mutate_the_element():
    screen = _screen()
    before = copy.deepcopy(screen.json_data)
    screen.clean_data()
    assert screen.json_data == before


def test_text_fields_round_trip():
    screen = _screen()
    screen.properties['conditions'] = '37 °C, 5 % CO2'
    screen.properties['result'] = 'two hits'
    data = screen.clean_data()
    assert (data['conditions'], data['result']) == ('37 °C, 5 % CO2', 'two hits')


def test_adding_and_removing_links():
    screen = _screen()
    plate, plan = _linked(Wellplate, 900), _linked(ResearchPlan, 901)
    screen.add_wellplate(plate).add_wellplate(plate).add_research_plan(plan)
    data = screen.clean_data()
    assert data['wellplate_ids'].count(900) == 1
    assert 901 in data['research_plan_ids']
    screen.remove_wellplate(plate).remove_research_plan(plan)
    data = screen.clean_data()
    assert 900 not in data['wellplate_ids'] and 901 not in data['research_plan_ids']


def test_removing_every_wellplate_sends_an_empty_list():
    """The server unlinks whatever is missing from `wellplate_ids`, so empty must be sent, not omitted."""
    screen = _screen()
    for plate in list(screen.wellplates):
        screen.remove_wellplate(plate)
    assert screen.clean_data()['wellplate_ids'] == []


@pytest.mark.parametrize('cls, add', [(Wellplate, 'add_wellplate'), (ResearchPlan, 'add_research_plan')])
def test_an_unsaved_element_cannot_be_linked(cls, add):
    with pytest.raises(ValueError, match='Save the'):
        getattr(_screen(), add)(_linked(cls, None))


def test_new_research_plan_needs_a_saved_screen():
    payload = json.load(open(FIXTURE))
    payload['id'] = None
    with pytest.raises(ValueError, match='Save the screen'):
        _screen(payload).new_research_plan(type('_Col', (), {'id': 1})())
