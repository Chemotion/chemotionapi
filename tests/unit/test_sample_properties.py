import json
import os
from types import SimpleNamespace

import pytest

import chemotion_api.elements.empty_elements as empty_elements
from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.sample import Molecule, Sample
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


def test_set_amount_without_stored_unit():
    # Issue: samples without a persisted amount crashed with AttributeError
    sample = _sample(target_amount_unit=None, target_amount_value=None)
    sample.set_amount(None)
    assert sample.properties['target_amount'].to_dict() == {'value': 0.0, 'unit': 'g'}


def test_append_material_without_amount():
    ref = _sample(1, reference=True)
    product = _sample(2, real_amount_unit=None, real_amount_value=None)
    reaction = _reaction([ref])
    product.reaction = reaction
    product.role_in_reaction = 'products'
    reaction.properties['products'].after_append(product)
    assert product.properties['real_amount']['unit'] == 'g'


def test_unknown_unit_message():
    with pytest.raises(ValueError, match='Allowed units'):
        _sample().set_amount(1, QuantityUnit.Equivalent)


def test_temperature_profile_of_new_reaction():
    reaction = _reaction([])
    reaction.properties['temperature'].add_time_point(1, 2, 3, 100)
    assert reaction.properties['temperature']['data'] == [{'time': '01:02:03', 'value': '100'}]


def test_partial_element_loads_before_access(monkeypatch):
    # Issue: listing elements were saved with their incomplete listing data
    listing = _sample_json(3, description=None, target_amount_unit=None, target_amount_value=None)
    full = _sample_json(3, description='Stored cold', target_amount_value=2.0)
    sample = Sample(SEGMENTS, SESSION, json_data=listing)
    sample.mark_partial()
    loads = []
    monkeypatch.setattr(sample, '_load_data_from_server', lambda: loads.append(1) or (None, full))
    assert sample.short_label == 'S-3' and loads == []
    sample.set_amount(1.5, QuantityUnit.Gram)
    assert loads == [1]
    assert sample.properties['description'] == 'Stored cold'
    assert sample.properties['target_amount']['value'] == 1.5
    sample.properties['description'] = 'x'
    assert loads == [1]


def test_molecule_density_is_copied_to_sample_without_density_or_molarity():
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.789})
    assert sample.properties['density'] == 0.789
    assert QuantityUnit.Liter in sample.allowed_quantity_units()


def test_molecule_molarity_is_copied_to_sample():
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0, 'molarity': 2.5})
    assert (sample.properties['density'], sample.properties['molarity'].to_dict()) == (0, {'value': 2.5, 'unit': 'M'})
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'molarity': {'value': 0.1, 'unit': 'mM'}})
    assert sample.properties['molarity'].to_dict() == {'value': 0.1, 'unit': 'mM'}


def test_molecule_does_not_overwrite_sample_density_or_molarity():
    sample = _sample(density=1.2)
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.789, 'molarity': 2.5})
    assert (sample.properties['density'], sample.properties['molarity']['value']) == (1.2, 0)
    sample = _sample(molarity_value=0.5)
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.789})
    assert (sample.properties['density'], sample.properties['molarity']['value']) == (0, 0.5)


def test_molecule_without_density_or_molarity_changes_nothing():
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.0})
    assert (sample.properties['density'], sample.properties['molarity']['value']) == (0, 0)


def test_append_no_split_assigns_reaction_role_and_position():
    first, second = _sample(1), _sample(2, target_amount_unit=None, target_amount_value=None)
    reaction = _reaction([first, second])
    assert reaction.starting_materials[1] is second
    assert (second.reaction, second.role_in_reaction, second.properties['position']) == (
        reaction, 'starting_materials', 1)
    assert second.properties['target_amount'].to_dict() == {'value': 0.0, 'unit': 'g'}


def test_direct_build_computes_equivalents_and_yield():
    # Issue: materials added with append_no_split got no equivalents and products no yield
    ref, reactant, product = _sample(1), _sample(2), _sample(3)
    for sample, role, value, unit in ((ref, 'starting_materials', 0.002, QuantityUnit.Mole),
                                      (reactant, 'reactants', 0.003, QuantityUnit.Mole),
                                      (product, 'products', 0.1, QuantityUnit.Gram)):
        sample.role_in_reaction = role
        sample.set_amount(value, unit)
    reaction = _reaction([ref], [reactant])
    reaction.products.append_no_split(product)
    reaction.reference_sample = ref
    assert [m.properties['equivalent'] for m in (ref, reactant, product)] == pytest.approx([1, 1.5, 0.5])


def test_equivalent_without_reference_amount_is_unknown():
    ref, reactant = _sample(1, target_amount_value=0), _sample(2)
    _reaction([ref], [reactant])
    assert reactant.properties['equivalent'] is None


def test_product_amount_in_mol():
    product = _sample(2)
    reaction = _reaction([_sample(1)])
    reaction.products.append_no_split(product)
    product.set_amount(0.002, QuantityUnit.Mole)
    assert product.properties['real_amount'].to_dict() == {'value': 0.002, 'unit': 'mol'}
    assert product.gram == pytest.approx(0.2)


def test_molecule_attribute_access():
    molecule = Molecule({'id': 2, 'molecular_weight': 46.07})
    assert molecule.molecular_weight == molecule['molecular_weight'] == 46.07
    assert molecule.sum_formular is None
    with pytest.raises(AttributeError):
        _ = molecule.unknown_key
