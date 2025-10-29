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


def test_get_collection_from_reaction(instance_with_test_reaction: dict):
    logged_in_instance :Instance = instance_with_test_reaction['instance']
    col: Collection = instance_with_test_reaction['main_collection']
    reaction = logged_in_instance.get_reaction(1)
    assert logged_in_instance.get_collection_of_element(reaction).id == 11


def test_get_reaction_success(instance_with_test_reaction: dict):
    wp = instance_with_test_reaction['instance'].get_reaction(instance_with_test_reaction['reaction'].id)
    assert wp.properties['starting_materials'][0].id != instance_with_test_reaction.get('sample_ids')[0]


def test_set_reaction_success(instance_with_test_reaction: dict):
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
    reaction.properties['purification_solvents'].append_no_split(solv)
    solv = col.new_solvent('Ethanol')
    solv.properties['target_amount']['value'] = 0.5
    solv.properties['target_amount']['unit'] = 'l'
    solv.save()
    reaction.properties['solvents'].append_no_split(solv)

    reaction.save()

def test_get_reaction_from_sample(instance_with_test_reaction: dict):
    logged_in_instance :Instance = instance_with_test_reaction['instance']
    reaction  = instance_with_test_reaction['reaction']
    sample = logged_in_instance.get_sample(reaction.properties['starting_materials'][0].id)
    assert sample.reaction.id == 2
    assert sample.reaction.properties['starting_materials'][0].id == sample.id
    assert reaction.properties['starting_materials'][0].reaction.id == reaction.id

def test_get_reaction_role_of_sample(instance_with_test_reaction: dict):
    logged_in_instance :Instance = instance_with_test_reaction['instance']
    reaction  = instance_with_test_reaction['reaction']
    s1 = logged_in_instance.get_sample(reaction.properties['starting_materials'][0].id)
    assert s1.role_in_reaction == 'starting_materials'
    assert s1.role_in_reaction == reaction.properties['starting_materials'][0].role_in_reaction