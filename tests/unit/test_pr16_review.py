"""Fixes from the review of PR #16 (2026-11-13). Each test reproduces the reported failure."""
import json
import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_sample_properties import SEGMENTS, SESSION  # noqa: E402

import chemotion_api  # noqa: E402
from chemotion_api.elements.reaction import Reaction  # noqa: E402
from chemotion_api.elements.screen import Screen  # noqa: E402

EMPTY = os.path.join(os.path.dirname(chemotion_api.__file__), 'elements', 'empty_elements')


def _reaction(**fields):
    data = {'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [], 'reactants': [],
            'products': [], 'solvents': [], 'purification_solvents': []} | fields
    reaction = Reaction(SEGMENTS, SESSION, json_data=data)
    reaction._data_loaded = True
    return reaction


# --- screens: link edits on a listed screen -----------------------------------------------------

def test_a_link_added_to_a_listed_screen_is_saved():
    with open(os.path.join(EMPTY, 'screen.json')) as f:
        full = json.load(f) | {'id': 5, 'name': 'S', 'wellplates': [{'id': 1}], 'research_plans': [],
                               'container': None, 'segments': [], 'attachments': []}
    sent = {}

    class Server:
        _host_url = 'http://x'
        schema_manager = SESSION.schema_manager

        def get(self, url, **kw):
            return SimpleNamespace(status_code=200, json=lambda: {'screen': full, 'attachments': []})

        def put(self, url, data=None, **kw):
            sent['body'] = json.loads(data)
            return SimpleNamespace(status_code=200, json=lambda: {'screen': full})

    listed = {'id': 5, 'type': 'screen', 'name': 'S', 'wellplates': [], 'research_plans': []}
    screen = Screen(SEGMENTS, Server(), json_data=listed)
    screen.mark_partial()
    screen.wellplate_ids.append(2)
    screen.save()
    assert sent['body']['wellplate_ids'] == [1, 2]


# --- rich text can be cleared -------------------------------------------------------------------

def test_assigning_none_clears_a_rich_text_property():
    reaction = _reaction(observation={'ops': [{'insert': 'seen\n'}]})
    reaction.properties['observation'] = None
    assert reaction.properties['observation'] == {'ops': [{'insert': '\n'}]}


# --- vessel size --------------------------------------------------------------------------------

def test_a_reaction_stored_with_a_bare_vessel_size_loads():
    """Clients before 401.0 could store a bare number."""
    assert _reaction(vessel_size=200).properties['vessel_size'] == {'amount': 200.0, 'unit': 'ml'}


def test_a_vessel_size_mapping_without_a_unit_keeps_the_current_unit():
    reaction = _reaction(vessel_size={'amount': 1, 'unit': 'l'})
    reaction.properties['vessel_size'] = {'amount': 2}
    assert reaction.properties['vessel_size'] == {'amount': 2.0, 'unit': 'l'}


# --- reading server data does not fail on one unexpected value ----------------------------------

def test_an_unexpected_value_from_the_server_is_kept_not_fatal(caplog):
    with open(os.path.join(EMPTY, 'screen.json')) as f:
        data = json.load(f) | {'id': 5, 'name': ['not', 'a', 'string'], 'conditions': '37 °C'}
    with caplog.at_level(logging.WARNING):
        screen = Screen(SEGMENTS, SESSION, json_data=data)
        screen._data_loaded = True
        props = screen.properties
    assert props['name'] == ['not', 'a', 'string'] and props['conditions'] == '37 °C'
    assert "'name'" in caplog.text
    with pytest.raises(Exception):
        screen.properties['name'] = ['still', 'refused']


# --- collection export: the right notification ----------------------------------------------------

@pytest.mark.parametrize('text, label, expected', [
    ('Collection Export: ["NMR"] processed successfully. 2026-11-15', 'NMR', True),
    ('Collection Export: ["NMR 2024"] processed successfully. 2026-11-15', 'NMR', False),
    ('Collection Export: There was an issue while processing ["NMR"].', 'NMR', True),
    ('Collection Import: ["NMR"] processed successfully.', 'NMR', False),
    ('Collection Export: ["say \\"hi\\""] processed successfully.', 'say "hi"', True),
])
def test_an_export_notification_matches_only_its_own_collection(text, label, expected):
    from chemotion_api.utils.collection_zip import _is_export_of
    assert _is_export_of(text, label) is expected


# --- molecule names -----------------------------------------------------------------------------

def _names_session(store):
    def get(url, params=None, **kw):
        if params.get('new_name'):
            store.append(params['new_name'])
        rows = [{'value': i, 'label': n, 'desc': 'defined by user'} for i, n in enumerate(store)]
        return SimpleNamespace(status_code=200, json=lambda: {'molecules': rows})
    return SimpleNamespace(get=get)


def test_add_name_returns_a_padded_name_as_the_eln_stores_it():
    from chemotion_api.elements.sample import MoleculeManager
    store = []
    assert MoleculeManager(_names_session(store)).add_name(1, '  Spirit ').name == 'Spirit'
    assert store == ['Spirit']


def test_add_name_refuses_a_semicolon_the_eln_would_split_on():
    from chemotion_api.elements.sample import MoleculeManager
    store = []
    with pytest.raises(ValueError, match=';'):
        MoleculeManager(_names_session(store)).add_name(1, 'a;b')
    assert store == [], 'nothing is sent'


# --- CLI image lookup ---------------------------------------------------------------------------

def _hub(*pages):
    return [MagicMock(status_code=200, json=MagicMock(return_value=p)) for p in pages]


def test_image_lookup_keeps_hyphenated_service_names():
    page = {'results': [{'name': 'eln-1.2'}, {'name': 'ketchersvc-sc-1.2'}], 'next': None}
    with patch('chemotion_api.commands.requests.get', side_effect=_hub(page)):
        from chemotion_api.commands import InstanceManager
        assert InstanceManager.get_image_of_versions('1.2')['ketchersvc-sc'] == 'ptrxyz/chemotion:ketchersvc-sc-1.2'


def test_image_lookup_without_any_eln_tag_raises_a_clear_error():
    page = {'results': [{'name': 'db-1.2'}], 'next': None}
    with patch('chemotion_api.commands.requests.get', side_effect=_hub(page)):
        from chemotion_api.commands import InstanceManager
        with pytest.raises(LookupError, match='eln-'):
            InstanceManager.get_image_of_versions()


# --- second review round: the duplicated code is shared ---------------------------------------

def test_proposed_field_writes_into_a_copy_and_creates_missing_mappings():
    from chemotion_api.elements.abstract_element import proposed_field
    stored = {'a': {'b': 1}}
    assert proposed_field(stored, ['f', 'a', 'c', 'd'], 2) == {'a': {'b': 1, 'c': {'d': 2}}}
    assert stored == {'a': {'b': 1}}, 'the stored field is untouched'
    assert proposed_field(stored, ['f'], 5) == 5


def test_proposed_field_refuses_to_walk_into_a_scalar():
    from chemotion_api.elements.abstract_element import proposed_field
    with pytest.raises(ValueError, match='stored as a single value'):
        proposed_field({'a': 1}, ['f', 'a', 'b'], 2)
    with pytest.raises(ValueError, match='stored as a single value'):
        proposed_field(3.0, ['f', 'x'], 2)


def test_every_builtin_type_has_a_url_and_a_class():
    from chemotion_api.elements import _BUILTIN_ELEMENT_CLASSES
    from chemotion_api.elements.abstract_element import BUILTIN_ELEMENT_URLS, AbstractElement
    assert set(_BUILTIN_ELEMENT_CLASSES) == set(BUILTIN_ELEMENT_URLS)
    assert AbstractElement.get_url('cell_line') == '/api/v1/cell_lines'
    assert AbstractElement.get_response_key('cell_line') == 'cell_line'
    assert AbstractElement.get_url('my_generic') == '/api/v1/generic_elements'
    assert AbstractElement.get_response_key('my_generic') == 'element'


def test_a_type_the_server_does_not_have_is_named():
    from chemotion_api.collection import AbstractCollection
    collection = AbstractCollection.__new__(AbstractCollection)
    root = SimpleNamespace(_element_manager=SimpleNamespace(all_classes={}), _session=None)
    collection.get_root = lambda: root
    with pytest.raises(ValueError, match='no element type "screen"'):
        collection.get_screens()
    instance = chemotion_api.Instance.__new__(chemotion_api.Instance)
    with patch.object(chemotion_api.Instance, 'all_element_classes', new={}):
        with pytest.raises(ValueError, match='no element type "screen"'):
            instance.get_screen(1)
