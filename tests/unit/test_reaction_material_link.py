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


def test_reloading_a_material_keeps_its_link_fields():
    material = _sample_json(2) | {'reference': True, 'equivalent': 1.0, 'position': 0}
    sample = Sample(SEGMENTS, SESSION, json_data=material)
    sample.reaction = SimpleNamespace()     # bound to a reaction
    standalone = _sample_json(2)             # /samples/:id: no link fields at all
    for key in ('reference', 'equivalent', 'position'):
        standalone.pop(key, None)
    sample._set_json_data(standalone)
    assert sample.json_data['reference'] is True
    assert sample.json_data['equivalent'] == 1.0


def test_a_value_the_server_sends_is_not_overridden():
    sample = Sample(SEGMENTS, SESSION, json_data=_sample_json(2) | {'reference': True})
    sample.reaction = SimpleNamespace()
    sample._set_json_data(_sample_json(2) | {'reference': False})
    assert sample.json_data['reference'] is False


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
