"""Saving analyses without the element (M3.5)."""
import pytest

pytestmark = pytest.mark.integration


def test_save_and_delete_analyses_only(instance_with_collection):
    col = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.properties['name'] = 'kept'
    sample.analyses.add_analyses('first')
    sample.save()
    sample.load()

    sample.properties['name'] = 'not sent'
    sample.analyses.by_name('first')['status'] = 'Confirmed'
    sample.analyses.add_analyses('second')
    sample.save_analyses()
    assert all(a.id is not None and not a.is_new for a in sample.analyses)

    sample.load()
    assert sample.properties['name'] == 'kept'
    assert {a['name']: a.get('status') for a in sample.analyses} == {'first': 'Confirmed', 'second': None}

    sample.delete_analysis(sample.analyses.by_name('first'))
    assert [a['name'] for a in sample.analyses] == ['second']
    sample.load()
    assert [a['name'] for a in sample.analyses] == ['second']
