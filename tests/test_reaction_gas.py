from cmath import isnan

import pytest

from chemotion_api import Instance, Reaction
from chemotion_api.elements.utils import GasType


@pytest.fixture()
def instance_with_test_reaction(instance_with_test_samples):
    i: Instance = instance_with_test_samples['instance']
    col = instance_with_test_samples['main_collection']
    sol = col.new_solvent('Acetone')
    sol.set_amount(300, 'l')
    reactant = i.get_sample(2)
    st_mt = col.new_sample_smiles('N')
    pr_mt = col.new_sample_smiles('NO')
    reaction = col.new_reaction()
    reaction.reactants.append(reactant)
    reaction.starting_materials.append(st_mt)
    reaction.products.append(pr_mt)
    reaction.solvents.append(sol)
    reaction.save()
    reaction.reactants[0].set_amount(200, 'mol')
    reaction.reactants[0].properties['density'] = 2
    reaction.starting_materials[0].set_amount(100, 'mol')

    reaction.products[0].set_amount(1000, 'g')
    reaction.products[0].properties['coefficient'] = 2
    reaction.save()
    yield instance_with_test_samples | {
        'reaction': reaction
    }

def test_to_gas_model(instance_with_test_reaction):
    reaction: Reaction = instance_with_test_reaction['reaction']
    try:
        reaction.starting_materials[0].gas_type = 'gas'
        assert False
    except ValueError:
        pass
    reaction.starting_materials[0].gas_type = 'off'
    reaction.gas_schema = True
    try:
        reaction.starting_materials[0].gas_type = GasType.GAS
        assert False
    except ValueError:
        pass
    try:
        reaction.starting_materials[0].gas_type = GasType.CATALYST
        assert False
    except ValueError:
        pass
    reaction.starting_materials[0].gas_type = GasType.FEEDSTOCK
    reaction.reactants[0].gas_type = GasType.FEEDSTOCK
    assert reaction.starting_materials[0].gas_type == GasType.OFF
    reaction.starting_materials[0].gas_type = GasType.CATALYST
    assert reaction.starting_materials[0].gas_type == GasType.CATALYST
    reaction.reactants[0].gas_type = GasType.OFF
    assert reaction.starting_materials[0].gas_type == GasType.OFF
    reaction.products[0].gas_type = GasType.GAS

def prepare_reaction(instance_with_test_reaction):
    reaction: Reaction = instance_with_test_reaction['reaction']
    reaction.gas_schema = True
    reaction.starting_materials[0].gas_type = GasType.FEEDSTOCK
    reaction.products[0].gas_type = GasType.GAS
    reaction.reactants[0].set_ref(True)
    reaction.reactants[0].set_amount(100, 'g')
    reaction.starting_materials[0].set_amount(50, 'l')
    return reaction

def test_FEEDSTOCK_amount(instance_with_test_reaction):
    reaction = prepare_reaction(instance_with_test_reaction)
    reaction.save()
    sm = reaction.starting_materials[0]
    assert int(sm.mol*1000) == 2071
    assert isnan(sm.gram)
    assert sm.liter == 50
    assert int(sm.equivalent * 10000) == 3527


def test_gas_amount(instance_with_test_reaction):
    reaction: Reaction = prepare_reaction(instance_with_test_reaction)
    gp = reaction.products[0].properties.get('gas_phase_data')
    reaction.properties['vessel_size'] = 200
    gp.ppm = 200
    gp.temperature_in_k = 2
    assert int(reaction.products[0].equivalent * 10000) == 294
    assert int(reaction.products[0].mol * 10000) == 2436
    assert int(reaction.products[0].liter * 10000) == 60551


def test_CAT_amount(instance_with_test_reaction):
    reaction: Reaction = prepare_reaction(instance_with_test_reaction)
    gp = reaction.products[0].properties.get('gas_phase_data')
    reaction.properties['vessel_size'] = 200
    gp.ppm = 200
    gp.temperature_in_k = 2
    assert int(reaction.products[0].equivalent * 10000) == 294
    assert int(reaction.products[0].mol * 10000) == 2436
    assert int(reaction.products[0].liter * 10000) == 60551

