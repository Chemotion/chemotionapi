import pytest

from chemotion_api import Instance
from chemotion_api.collection import Collection


@pytest.fixture()
def instance_with_test_reaction(instance_with_test_samples):
    ra = instance_with_test_samples['main_collection'].new_reaction()
    s1 = instance_with_test_samples['instance'].get_sample(instance_with_test_samples.get('sample_ids')[0])
    ra.properties['starting_materials'].append(s1)

    ra.save()
    yield instance_with_test_samples | {
        'reaction': ra
    }

def test_get_reaction_success(instance_with_test_reaction: dict):
    wp = instance_with_test_reaction['instance'].get_reaction(instance_with_test_reaction['reaction'].id)
    assert wp.properties['starting_materials'][0].id != instance_with_test_reaction.get('sample_ids')[0]


def test_set_reactoin_success(instance_with_test_reaction: dict):
    logged_in_instance :Instance = instance_with_test_reaction['instance']
    col: Collection = instance_with_test_reaction['main_collection']
    reaction  = instance_with_test_reaction['reaction']
    s2 = logged_in_instance.get_sample(instance_with_test_reaction.get('sample_ids')[1])
    s3 = logged_in_instance.get_sample(instance_with_test_reaction.get('sample_ids')[2])
    s4 = logged_in_instance.get_sample(instance_with_test_reaction.get('sample_ids')[3])
    s5 = logged_in_instance.get_sample(instance_with_test_reaction.get('sample_ids')[4])

    reaction.properties['starting_materials'].append(s2)
    reaction.properties['reactants'].append(s3)
    reaction.properties['products'].append(s4)
    reaction.properties['products'].append(s5)
    solv = col.new_solvent('CDCl3')
    reaction.properties['purification_solvents'].append(solv)
    solv = col.new_solvent('Ethanol')
    solv.save()
    reaction.properties['solvents'].append(solv)

    reaction.save()


    pass
