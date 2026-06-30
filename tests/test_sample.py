from datetime import datetime
from random import randint

import pytest

from chemotion_api import Instance
from chemotion_api.collection import Collection


def test_get_sample_success(instance_with_test_samples: dict):
    instance_with_test_samples.get('instance').get_sample(instance_with_test_samples.get('sample_ids')[0])

def test_new_sample_success(instance_with_collection):
    logged_in_instance = instance_with_collection['instance']
    m_col = instance_with_collection['main_collection']

    sample = m_col.new_sample()
    m = logged_in_instance.molecule().create_molecule_by_smiles('B')
    sample.molecule = m
    sample.properties['boiling_point_lowerbound'] = 0.5
    sample.properties['boiling_point_upperbound'] = 1
    sample.properties['melting_point_lowerbound'] = 0.55
    sample.properties['melting_point_upperbound'] = 15
    sample.properties['name'] = f"test_app{randint(1, 10)}"
    sample.properties['description'] = """This is a test sample\nSmiles: B"""
    sample.properties['stereo'] = {"abs": "(S)", "rel": "p-geminal"}
    sample.properties['location'] = "Test-shelf"
    sample.properties['molarity']['value'] = 0.3
    sample.properties['solvent'].add_new_smiles('B')
    sample.properties['solvent'].add_new_name('CDCl3')
    sample.save()
    sample_a = logged_in_instance.get_sample(sample.id)
    assert sample_a.id == sample.id
    assert sample_a.properties['solvent'][0]['label'] == 'borane'
    assert sample_a.properties['solvent'][1]['smiles'] == '[2H]C(Cl)(Cl)Cl'

    test = logged_in_instance.get_json_ld_id(sample_a.json_ld['@id'])
    assert test.json_ld == sample_a.json_ld

def test_new_sample_decupled_success(instance_with_collection):
    m_col = instance_with_collection['main_collection']
    sample_de = m_col.new_sample()
    sample_de.toggle_decoupled()
    sample_de.save()
    assert sample_de.id is not None
    pass

def test_solvents(logged_in_instance, delete_col_prefix):
    solver_list = logged_in_instance.get_solvent_list()
    assert len(solver_list) == 190
    assert '1-Butyl-3-methylimidazolium Bis(trifluoromethanesulfonyl)imide' in solver_list

    col = logged_in_instance.get_root_collection().get_or_create_collection(f'/{delete_col_prefix}test_col')
    solv = col.new_solvent('CDCl3')
    solv.save()
    assert solv.properties['external_label'] == 'CDCl3'
    assert solv.id is not None
    assert int(solv.id) > 0

    with pytest.raises(KeyError) as e:
        solv = col.new_solvent('XXX')


def test_iter_sample(instance_with_test_samples: dict):
    main_collection: Collection = instance_with_test_samples['main_collection']
    samples = main_collection.get_samples(per_page=2)
    ids = []
    for s in samples.iter_pages():
        for sample in s:
            assert sample.id not in ids
            ids.append(sample.id)
        assert len(s) <= 5
    page = samples.page
    s = samples.prev_page()
    assert s.page == page -1
    for sample in s:
        assert sample.id in ids
        assert len(s) <= 5


    s = samples.next_page()
    assert s.page == page
    for sample in s:
        assert sample.id in ids
        assert len(s) <= 5

def test_get_collection_from_sample(instance_with_test_samples: dict):
    logged_in_instance = instance_with_test_samples['instance']
    col: Collection = instance_with_test_samples['main_collection']
    sample  =  instance_with_test_samples.get('instance').get_sample(instance_with_test_samples.get('sample_ids')[0])
    assert logged_in_instance.get_collection_of_element(sample).id == col.id

def test_filter_collection(instance_with_test_samples: dict):
    logged_in_instance = instance_with_test_samples['instance']
    col: Collection = instance_with_test_samples['main_collection']
    assert len(col.get_samples(updated_to_date=datetime(2020, 1, 1))) == 0
    assert len(col.get_samples(updated_to_date=datetime(2060, 1, 1))) > 1
    assert len(col.get_samples(updated_from_date=datetime(2060, 1, 1))) == 0
    assert len(col.get_samples(updated_from_date=datetime(2025, 1, 1))) > 1

    assert len(col.get_samples(product_only=True)) == 0

    rea = col.new_reaction()

    samples = col.get_samples()

    rea.properties['starting_materials'].append(samples[0])
    rea.properties['products'].append(samples[1])
    rea.save()

    assert len(col.get_samples(product_only=True)) == 1