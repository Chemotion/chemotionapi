"""Sequence-based macromolecule samples on a live ELN (M4.4)."""
import uuid

import pytest

pytestmark = pytest.mark.integration


def test_sbmm_sample_lifecycle(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    short_name = f'API{uuid.uuid4().hex[:5]}'
    sample = col.new_sbmm_sample()
    sample.properties['name'] = 'batch 1'
    sample.macromolecule.update(uniprot_derivation='uniprot_unknown', short_name=short_name,
                                sequence='KVFGRCELAAAMKRHGLDNYRG')
    sample.save()
    assert sample.macromolecule['id'] and sample.macromolecule['sequence_length'] == 22

    loaded = instance.get_sbmm_sample(sample.id)
    loaded.properties['concentration_value'] = 1.5
    loaded.properties['concentration_unit'] = 'mg/L'
    loaded.analyses.add_analyses('SDS-PAGE')
    loaded.save()
    again = instance.get_sbmm_sample(sample.id)
    assert (again.properties['concentration_value'], again.properties['concentration_unit']) == (1.5, 'mg/L')
    assert [a['name'] for a in again.analyses] == ['SDS-PAGE']

    found = [r for r in instance.search_macromolecules(short_name, 'protein_name') if r.get('id')]
    assert [r['id'] for r in found] == [sample.macromolecule['id']]
    assert instance.get_macromolecule(sample.macromolecule['id'])['short_name'] == short_name

    (sub,) = col.split_sbmm_samples(again)
    assert sub.short_label == f'{again.short_label}-1'
    assert {s.id for s in col.get_sbmm_samples()} == {sample.id, sub.id}
    assert sub.delete()


def test_sample_from_uniprot(instance_with_collection):
    col = instance_with_collection['main_collection']
    sample = col.new_sbmm_sample()
    try:
        sample.use_uniprot('P61626')
    except Exception as e:  # the stack may run without internet access
        pytest.skip(f'UniProt is not reachable from the ELN: {e}')
    sample.save()
    assert (sample.macromolecule['primary_accession'], sample.macromolecule['uniprot_derivation']) == (
        'P61626', 'uniprot')
