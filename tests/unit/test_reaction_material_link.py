"""A reaction material keeps its link to the reaction (reference, equivalent, coefficient …).

Found 2026-11-13: loading a reaction and saving it cleared its reference flag. The materials
fetched their own records from /samples/:id, which lack the link fields, and the save wrote the
loss back.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(__file__))
from test_sample_properties import SEGMENTS, SESSION, _sample_json  # noqa: E402

from chemotion_api.elements.reaction import Reaction  # noqa: E402
from chemotion_api.elements.sample import Sample  # noqa: E402


def _loaded_reaction(material):
    reaction = Reaction.__new__(Reaction)
    reaction._data_loaded = True            # as during load(): set before the payload is parsed
    Reaction.__init__(reaction, SEGMENTS, SESSION, json_data={
        'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [material], 'reactants': [],
        'products': [], 'solvents': [], 'purification_solvents': []})
    return reaction


def test_materials_of_a_loaded_reaction_are_not_refetched():
    material = _sample_json(2) | {'reference': True, 'equivalent': 1.0, 'coefficient': 2.0}
    reaction = Reaction(SEGMENTS, SESSION, json_data={
        'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [], 'reactants': [],
        'products': [], 'solvents': [], 'purification_solvents': []})
    reaction._data_loaded = True
    reaction._set_json_data(reaction.json_data | {'starting_materials': [material]})
    mat = reaction.starting_materials[0]
    assert mat._data_loaded, 'no fetch of /samples/:id for a material of a loaded reaction'
    assert mat.properties['reference'] is True
    assert mat.properties['coefficient'] == 2.0


class _Server:
    """Answers the reaction's and the sample's detail routes and records what was asked."""

    def __init__(self, reaction_record, sample_record):
        self.urls = []
        self._routes = {'/api/v1/reactions/1.json': {'reaction': reaction_record},
                        '/api/v1/samples/2.json': {'sample': sample_record}}
        self._host_url = SESSION._host_url
        self.schema_manager = SESSION.schema_manager

    def get(self, url, **kwargs):
        self.urls.append(url)
        return SimpleNamespace(status_code=200, json=lambda: self._routes[url])


def _unloaded_reaction(server, material):
    """A reaction built from a payload, not loaded: its materials load lazily."""
    return Reaction(SEGMENTS, server, json_data={
        'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [material], 'reactants': [],
        'products': [], 'solvents': [], 'purification_solvents': []})



def _material(reaction):
    """The parsed material, read without loading the reaction (whose own load would mark it loaded)."""
    return reaction._properties_data['starting_materials'][0]

def test_a_material_loads_from_its_reactions_record():
    """Review of PR #16: the link loss was patched twice (materials marked loaded, link fields
    merged back from the old payload). The root cause was that a material reloaded itself from
    /samples/:id, which has no link. It now reads the reaction's record."""
    link = {'reference': True, 'equivalent': 1.0, 'coefficient': 2.0, 'position': 0}
    material = _sample_json(2) | link
    standalone = {k: v for k, v in _sample_json(2).items() if k not in link}
    server = _Server({'id': 1, 'starting_materials': [material | {'name': 'fresh'}]}, standalone)
    reaction = _unloaded_reaction(server, material)
    mat = _material(reaction)
    assert not mat._data_loaded
    mat.load()
    assert server.urls == ['/api/v1/reactions/1.json']
    assert mat.json_data['name'] == 'fresh'
    assert mat.properties['reference'] is True
    assert mat.properties['coefficient'] == 2.0


def test_a_sample_the_reaction_no_longer_lists_loads_its_own_record():
    material = _sample_json(2) | {'reference': True}
    server = _Server({'id': 1, 'starting_materials': []}, _sample_json(2) | {'name': 'own'})
    mat = _material(_unloaded_reaction(server, material))
    mat.load()
    assert server.urls == ['/api/v1/reactions/1.json', '/api/v1/samples/2.json']
    assert mat.json_data['name'] == 'own'


def test_a_direct_write_on_an_unloaded_material_survives_the_load():
    """Review of PR #16: `_properties` loaded only listed elements, so each Sample writer called
    `_ensure_loaded()` itself. It now loads any element that is not loaded yet, so a writer that
    touches `_properties` first (set_ref without the handler, here) keeps its write."""
    material = _sample_json(2) | {'reference': False}
    server = _Server({'id': 1, 'starting_materials': [material]}, _sample_json(2))
    mat = _material(_unloaded_reaction(server, material))
    mat.set_ref(True, check_ref=False)
    assert server.urls == ['/api/v1/reactions/1.json'], 'loaded once, before the write'
    assert mat.properties['reference'] is True


def test_a_reaction_reread_by_save_keeps_its_materials_loaded(monkeypatch):
    """save() re-reads an element that was never fully loaded. That parse must count as a full
    load, as load() does: before, the materials were built as incomplete and the record was
    fetched a second time (review of PR #16)."""
    material = _sample_json(2) | {'reference': True, 'equivalent': 1.0}
    record = {'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [material], 'reactants': [],
              'products': [], 'solvents': [], 'purification_solvents': []}
    reaction = Reaction(SEGMENTS, SESSION, json_data=dict(record) | {'starting_materials': []})
    reaction._data_loaded = False
    fetches = []
    monkeypatch.setattr(reaction, '_load_data_from_server', lambda: fetches.append(1) or (None, record))
    seen = {}

    def stop(*a, **k):
        seen['materials'] = [m._data_loaded for m in reaction.starting_materials]
        raise RuntimeError('stop before sending')
    monkeypatch.setattr(reaction, 'clean_data', stop)
    from chemotion_api.elements.abstract_element import AbstractElement
    try:
        # The base save() itself: Reaction.save() happens to load first (update_equivalent reads
        # the properties), which hides this branch today.
        AbstractElement.save(reaction)
    except RuntimeError:
        pass
    assert seen['materials'] == [True]
    assert len(fetches) == 1, 'the record is fetched once'
