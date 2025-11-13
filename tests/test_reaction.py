import json

import pytest

from chemotion_api import Instance
from chemotion_api.collection import Collection
from chemotion_api.elements.utils import calculate_quantity, QuantityUnit
from chemotion_api.utils import fixeddict_serializer


@pytest.fixture()
def instance_with_test_reaction(instance_with_test_samples):
    ra = instance_with_test_samples['main_collection'].new_reaction()
    s1 = instance_with_test_samples['instance'].get_sample(instance_with_test_samples.get('sample_ids')[0])
    ra.properties['starting_materials'].append(s1)

    ra.save()
    yield instance_with_test_samples | {
        'reaction': ra
    }


def test_get_collection_from_reaction(instance_with_test_reaction: dict):
    logged_in_instance: Instance = instance_with_test_reaction['instance']
    col: Collection = instance_with_test_reaction['main_collection']
    reaction = logged_in_instance.get_reaction(1)
    assert logged_in_instance.get_collection_of_element(reaction).id == 11


def test_get_reaction_success(instance_with_test_reaction: dict):
    wp = instance_with_test_reaction['instance'].get_reaction(instance_with_test_reaction['reaction'].id)
    assert wp.properties['starting_materials'][0].id != instance_with_test_reaction.get('sample_ids')[0]


def test_set_reaction_success(instance_with_test_reaction: dict):
    logged_in_instance: Instance = instance_with_test_reaction['instance']
    col: Collection = instance_with_test_reaction['main_collection']
    reaction = col.new_reaction()
    sample = col.new_sample_smiles('N')
    reaction.properties['products'].append_no_split(sample)

    data = reaction.clean_data()

    json_dumps_data = json.dumps(data, default=fixeddict_serializer)
    with open('../example.json', 'w') as outfile:
        outfile.write(json_dumps_data)
    pass
    reaction.save()


def test_get_reaction_from_sample(instance_with_test_reaction: dict):
    logged_in_instance: Instance = instance_with_test_reaction['instance']
    reaction = instance_with_test_reaction['reaction']
    sample = logged_in_instance.get_sample(reaction.properties['starting_materials'][0].id)
    assert sample.reaction.id == reaction.id
    assert sample.reaction.properties['starting_materials'][0].id == sample.id
    assert reaction.properties['starting_materials'][0].reaction.id == reaction.id


def test_calculate_amount_from_mol(instance_with_test_reaction: dict):
    in_m = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Mole,
        output_unit=QuantityUnit.Mole,
        molecular_weight=17.030520,
        purity=0.5,
        molarity=3,
        density=0
    )
    assert in_m == 2
    in_l = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Mole,
        output_unit=QuantityUnit.Liter,
        molecular_weight=17.030520,
        purity=.5,
        molarity=3,
        density=0
    )
    assert int(in_l * 100) == 66
    in_l = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Mole,
        output_unit=QuantityUnit.Liter,
        molecular_weight=17.030520,
        purity=.5,
        molarity=0,
        density=3
    )
    assert int(in_l * 10000) == 227
    in_g = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Mole,
        output_unit=QuantityUnit.Gram,
        molecular_weight=17.030520,
        purity=0.5,
        molarity=3,
        density=0
    )
    assert int(in_g * 100) == 6812


def test_calculate_amount_from_gram(instance_with_test_reaction: dict):
    in_m = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Gram,
        output_unit=QuantityUnit.Mole,
        molecular_weight=17.030520,
        purity=0.5,
        molarity=3,
        density=0
    )
    assert int(in_m * 1000) == 58
    in_l = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Gram,
        output_unit=QuantityUnit.Liter,
        molecular_weight=17.030520,
        purity=.5,
        molarity=3,
        density=0
    )
    assert int(in_l * 100000) == 1957
    in_l = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Gram,
        output_unit=QuantityUnit.Liter,
        molecular_weight=17.030520,
        purity=.5,
        molarity=0,
        density=3
    )
    assert int(in_l * 100000) == 66
    in_g = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Gram,
        output_unit=QuantityUnit.Gram,
        molecular_weight=17.030520,
        purity=0.5,
        molarity=3,
        density=0
    )
    assert in_g == 2



def test_calculate_amount_from_liter(instance_with_test_reaction: dict):
    in_l = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Liter,
        output_unit=QuantityUnit.Liter,
        molecular_weight=17.030520,
        purity=0.5,
        molarity=3,
        density=0
    )
    assert in_l == 2

    in_g = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Liter,
        output_unit=QuantityUnit.Gram,
        molecular_weight=17.030520,
        purity=.5,
        molarity=3,
        density=0
    )
    assert int(in_g * 10)  == 1021

    in_m = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Liter,
        output_unit=QuantityUnit.Mole,
        molecular_weight=17.030520,
        purity=.5,
        molarity=3,
        density=0
    )
    assert in_m == 6

    in_g = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Liter,
        output_unit=QuantityUnit.Gram,
        molecular_weight=17.030520,
        purity=.5,
        molarity=0,
        density=3
    )
    assert in_g == 6000

    in_m = calculate_quantity(
        current_value=2,
        current_unit=QuantityUnit.Liter,
        output_unit=QuantityUnit.Mole,
        molecular_weight=17.030520,
        purity=.5,
        molarity=0,
        density=3
    )
    assert int(in_m * 10) == 1761


def test_get_reaction_amount(instance_with_test_reaction: dict):
    logged_in_instance: Instance = instance_with_test_reaction['instance']
    reaction = instance_with_test_reaction['reaction']
    reaction = instance_with_test_reaction['main_collection'].new_reaction()
    s1 = instance_with_test_reaction['main_collection'].new_sample_smiles('N')
    s2 = instance_with_test_reaction['main_collection'].new_sample_smiles('O')

    reaction.properties['starting_materials'].append(s1)
    reaction.properties['reactants'].append(s2)

    reaction.save()
