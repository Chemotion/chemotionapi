import json
import os
from types import SimpleNamespace

import pytest

import chemotion_api.elements.empty_elements as empty_elements
from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.sample import Sample
from chemotion_api.elements.utils import QuantityUnit

SESSION = SimpleNamespace(_host_url='http://localhost',
                          schema_manager=SimpleNamespace(generate_model_type=lambda *args: 'chemotion:type'))
SEGMENTS = SimpleNamespace(all_classes=[])


def _sample_json(sample_id, mw=100.0, **kwargs):
    with open(os.path.join(os.path.dirname(empty_elements.__file__), 'sample.json')) as f:
        data = json.load(f)
    data |= {'id': sample_id, 'short_label': f'S-{sample_id}', 'real_amount_unit': 'g',
             'molecule': {'id': 1, 'molecular_weight': mw}} | kwargs
    return data


def _sample(sample_id=1, **kwargs):
    return Sample(SEGMENTS, SESSION, json_data=_sample_json(sample_id, **kwargs))


def _reaction(starting_materials, reactants=()):
    """A reaction built offline; materials are added without splitting (which would need a server)."""
    reaction = Reaction(SEGMENTS, SESSION, json_data={
        'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [], 'reactants': [], 'products': [],
        'solvents': [], 'purification_solvents': []})
    for role, samples in (('starting_materials', starting_materials), ('reactants', reactants)):
        for sample in samples:
            sample.reaction = reaction
            sample.role_in_reaction = role
            reaction.properties[role].append_no_split(sample)
    return reaction


def test_standalone_sample_properties():
    sample = _sample()
    sample.properties['purity'] = 0.5
    sample.properties['coefficient'] = 2
    sample.properties['reference'] = True
    sample.properties['real_amount']['value'] = 3.7
    assert (sample.properties['purity'], sample.properties['coefficient']) == (0.5, 2)
    assert sample.properties['reference'] is True
    # A standalone sample keeps target and real amount independent
    assert sample.properties['real_amount']['value'] == 3.7
    assert sample.properties['target_amount']['value'] == 0
    with pytest.raises(ValueError):
        sample.properties['purity'] = 0


def test_amount_assignment_replaces_dict():
    sample = _sample()
    sample.properties['target_amount'] = {'value': 2, 'unit': 'mol'}
    assert sample.properties['target_amount'].to_dict() == {'value': 2, 'unit': 'mol'}


def test_amount_in_reaction_updates_equivalent():
    ref, reactant = _sample(1, reference=True), _sample(2)
    reaction = _reaction([ref], [reactant])
    ref.properties['target_amount']['value'] = 1.0  # 0.01 mol
    reactant.properties['target_amount']['value'] = 2.0  # 0.02 mol
    assert reaction.reference_sample is ref
    assert reactant.properties['equivalent'] == pytest.approx(2.0)
    reactant.set_amount(0.5, QuantityUnit.Equivalent)
    assert reactant.mol == pytest.approx(0.005)


def test_reference_defaults_to_first_material():
    first, second = _sample(1), _sample(2)
    reaction = _reaction([first, second])
    assert reaction.reference_sample is first
    assert first.properties['reference'] is True
    assert second.properties['reference'] is False


def test_reference_without_materials():
    assert _reaction([]).reference_sample is None


def test_unit_from_string():
    assert QuantityUnit.from_string('G') is QuantityUnit.Gram
    assert QuantityUnit.from_string(None) is None
