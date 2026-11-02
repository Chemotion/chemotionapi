import json
from math import isnan

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
    assert int(in_g * 10) == 1021

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
    reaction = instance_with_test_reaction['main_collection'].new_reaction()
    s1 = instance_with_test_reaction['main_collection'].new_sample_smiles('N')
    s2 = instance_with_test_reaction['main_collection'].new_sample_smiles('O')

    reaction.properties['starting_materials'].append(s1)
    reaction.properties['reactants'].append(s2)

    reaction.save()


def test_extended_reaction_amount(instance_with_test_reaction: dict):
    i = instance_with_test_reaction['instance']
    col = instance_with_test_reaction['main_collection']
    sol = col.new_solvent('Acetone')
    sol.set_amount(300, 'l')
    reactant = i.get_sample(2)
    st_mt = col.new_sample_smiles('N')
    pr_mt = col.new_sample_smiles('NO')
    st_mt.save()
    reaction = col.new_reaction()
    reaction.reactants.append(reactant)
    reaction.starting_materials.append(st_mt)
    reaction.products.append(pr_mt)
    reaction.solvents.append(sol)
    reaction.save()
    reaction.reactants[0].set_amount(200, 'mol')
    reaction.reactants[0].properties['density'] = 2
    reaction.starting_materials[0].set_amount(100, 'mol')
    reaction.save()
    mats = [*reaction.starting_materials, *reaction.reactants, *reaction.products]

    assert [mat.mol for mat in [*reaction.starting_materials, *reaction.reactants, *reaction.products]] == [100,
                                                                                                            200, 0]
    assert [mat.gram for mat in mats] == [1703.052, 3406.104, 0]

    assert isnan(reaction.starting_materials[0].liter)
    assert reaction.reactants[0].liter == 1.703052
    assert isnan(reaction.products[0].liter)

    # Nothing is flagged as the reference, so there is nothing for an equivalent to be relative
    # to. This read [0.5, 1, 0] only because the getter silently picked the last candidate — the
    # reactant — which the ELN never chooses.
    assert [mat.properties['equivalent'] for mat in mats] == [None, None, None]

    reaction.reference_sample = reaction.starting_materials[0]
    reaction.update_equivalent()
    assert [mat.properties['equivalent'] for mat in mats] == [1, 2, 0]

    reaction.products[0].set_amount(1000, 'g')
    reaction.products[0].properties['coefficient'] = 2
    reaction.save()

    assert [mat.mol for mat in [*reaction.starting_materials, *reaction.reactants, *reaction.products]] == [100,
                                                                                                            200,
                                                                                                            30.275580443428264]
    assert [mat.gram for mat in [*reaction.starting_materials, *reaction.reactants, *reaction.products]] == [
        1703.052, 3406.104, 1000]

    assert isnan(reaction.starting_materials[0].liter)
    assert reaction.reactants[0].liter == 1.703052
    assert isnan(reaction.products[0].liter)

    assert [mat.properties['equivalent'] for mat in
            [*reaction.starting_materials, *reaction.reactants, *reaction.products]] == [1, 2.0,
                                                                                         0.1513779022171413]


def test_reaction_yield_properties(instance_with_test_reaction: dict):
    logged_in_instance = instance_with_test_reaction['instance']
    col = instance_with_test_reaction['main_collection']
    reaction = col.new_reaction()
    st_mt = col.new_sample_smiles("[H][H]")
    st_mt.save()
    product = col.new_sample_smiles("O")
    product.save()
    reaction.starting_materials.append(st_mt)
    reaction.products.append(product)

    reaction.properties.yield_value = 92.5
    reaction.save()

    # Reload from backend
    reloaded_reaction = logged_in_instance.get_reaction(reaction.id)
    assert reloaded_reaction.properties.get('yield_value') == 92.5
    assert reloaded_reaction.properties.get('yield') == 92.5

    # Test setting via dictionary item access
    reloaded_reaction.properties['yield'] = 85.0
    assert reloaded_reaction.properties.yield_value == 85.0
    assert reloaded_reaction.properties.get('yield') == 85.0


