from random import randint

import pytest

from chemotion_api import Instance
from chemotion_api.collection import Collection


def test_get_sample_success(instance_with_test_samples: dict):
    instance_with_test_samples.get('instance').get_sample(instance_with_test_samples.get('sample_ids')[0])


def test_new_sample_success(logged_in_instance: Instance):
    col = logged_in_instance.get_root_collection()
    try:
        m_col = col.get_collection('/test_col')
    except:
        col.add_collection('/test_col')
        col.save()
        m_col = col.get_collection('/test_col')

    sample = m_col.new_sample()
    m = logged_in_instance.molecule().create_molecule_by_smiles('B')
    sample.molecule = m
    sample.properties['boiling_point_lowerbound'] = 0.5
    sample.properties['boiling_point_upperbound'] = 1
    sample.properties['melting_point_lowerbound'] = 0.55
    sample.properties['melting_point_upperbound'] = 15
    sample.properties['name'] = "test_app{}".format(randint(1, 10))
    sample.properties['description'] = """This is a test sample\nSmiles: B"""
    sample.properties['stereo'] = {"abs": "(S)", "rel": "p-geminal"}
    sample.properties['location'] = "Test-shelf"
    sample.properties['molarity']['value'] = 0.3
    sample.save()
    sample_a = logged_in_instance.get_sample(sample.id)
    assert sample_a.id == sample.id

def test_solvents(logged_in_instance):
    solver_list = logged_in_instance.get_solvent_list()
    assert len(solver_list) == 190
    assert '1-Butyl-3-methylimidazolium Bis(trifluoromethanesulfonyl)imide' in solver_list

    col = logged_in_instance.get_root_collection().get_or_create_collection('/test_col')
    solv = col.new_solvent('CDCl3')
    solv.save()
    assert solv.properties['name'] == 'Solvent: CDCl3'
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
        assert len(s) <= 2
    page = samples.page
    s = samples.prev_page()
    assert s.page == page -1
    for sample in s:
        assert sample.id in ids
        assert len(s) <= 2


    s = samples.next_page()
    assert s.page == page
    for sample in s:
        assert sample.id in ids
        assert len(s) <= 2

