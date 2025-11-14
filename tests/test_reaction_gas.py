import json

import pytest

from chemotion_api import Instance
from chemotion_api.collection import Collection
from chemotion_api.elements.utils import calculate_quantity, QuantityUnit
from chemotion_api.utils import fixeddict_serializer


@pytest.fixture()
def instance_with_test_reaction(instance_with_test_samples):
    i = instance_with_test_samples['instance']
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
    mats = [*reaction.starting_materials, *reaction.reactants, *reaction.products]

    reaction.products[0].set_amount(1000, 'g')
    reaction.products[0].properties['coefficient'] = 2
    reaction.save()
    yield instance_with_test_samples | {
        'reaction': reactant
    }

def test_to_gas_model(instance_with_test_samples):
    reaction = instance_with_test_samples['reaction']
    reaction.gas_mode = False