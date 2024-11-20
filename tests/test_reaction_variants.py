import os

import pytest


@pytest.fixture()
def instance_with_test_reaction(instance_with_test_samples):
    ra = instance_with_test_samples['main_collection'].new_reaction()
    s1 = instance_with_test_samples['instance'].get_sample(instance_with_test_samples.get('sample_ids')[0])
    ra.properties['starting_materials'].append(s1)
    ana = ra.analyses
    ana.add_analyses('T1')
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    ana.add_analyses('T2').add_dataset(os.path.join(data_dir, 'SG-V3545-6-13.cif'))
    ra.save()
    yield instance_with_test_samples | {
        'reaction': ra
    }


def test_reaction_variants(instance_with_test_reaction):
    ra = instance_with_test_reaction['instance'].get_reaction(1)
    assert len(ra.variations) == 2
    variant = ra.variations[0]
    assert variant.properties == {'duration': {'unit': 'Second(s)', 'value': 2},
                                  'temperature': {'unit': '°C', 'value': 1}}
    assert [x.sample.id for x in variant.starting_materials] == [2]
    assert [x.sample.id for x in variant.reactants] == [3]
    assert [x.sample.id for x in variant.products] == [4]


def test_add_variations(instance_with_test_reaction):
    ra = instance_with_test_reaction['instance'].get_reaction(1)
    ra.variations.add_new()
    ra.save(True)

    assert len(ra.variations) == 3
    variant = ra.variations[-1]
    assert variant.properties == {'duration': {'unit': 'Second(s)', 'value': 0},
                                  'temperature': {'unit': '°C', 'value': 0}}
    assert [x.sample.id for x in variant.starting_materials] == [2]
    assert [x.clean() for x in variant.starting_materials] == [{'amount': {'unit': 'mol', 'value': 0.0},
                                                                'aux': {'coefficient': 1,
                                                                        'equivalent': None,
                                                                        'isReference': False,
                                                                        'loading': None,
                                                                        'molarity': 0,
                                                                        'molecularWeight': 0,
                                                                        'purity': 1,
                                                                        'sumFormula': 'C7H12O6',
                                                                        'yield': None},
                                                                'mass': {'unit': 'g', 'value': 0.0},
                                                                'volume': {'unit': 'l', 'value': 0.0}}]
    assert [x.sample.id for x in variant.reactants] == [3]
    assert [x.clean() for x in variant.reactants] == [{'amount': {'unit': 'mol', 'value': 0.0},
                                                       'aux': {'coefficient': 1,
                                                               'equivalent': None,
                                                               'isReference': False,
                                                               'loading': None,
                                                               'molarity': 0,
                                                               'molecularWeight': 0,
                                                               'purity': 1,
                                                               'sumFormula': 'C7H12O6',
                                                               'yield': None},
                                                       'mass': {'unit': 'g', 'value': 0.022},
                                                       'volume': {'unit': 'l', 'value': 0.0}}]
    assert [x.sample.id for x in variant.products] == [4]
    assert [x.clean() for x in variant.products] == [{'amount': {'unit': 'mol', 'value': 0.0},
                                                      'aux': {'coefficient': 1,
                                                              'equivalent': None,
                                                              'isReference': False,
                                                              'loading': None,
                                                              'molarity': 0,
                                                              'molecularWeight': 0,
                                                              'purity': 1,
                                                              'sumFormula': 'C7H12O6',
                                                              'yield': None},
                                                      'mass': {'unit': 'g', 'value': None},
                                                      'volume': {'unit': 'l', 'value': 0.0}}]


def test_remove_variations(instance_with_test_reaction):
    ra = instance_with_test_reaction['instance'].get_reaction(1)
    v = ra.variations[-1]
    v_len =  len(ra.variations)
    assert ra.variations.remove(v)
    ra.save(True)
    assert len(ra.variations) == v_len - 1
