"""Server-side sample splits on a live ELN (M2.2)."""
import pytest

pytestmark = pytest.mark.integration


def test_split_two_samples_then_one_again(instance_with_collection):
    col = instance_with_collection['main_collection']
    a, b = col.new_sample_smiles('CCO'), col.new_sample_smiles('CCC')
    a.save()
    b.save()

    first = col.split_samples(a, b)
    assert [s.json_data['parent_id'] for s in first] == [a.id, b.id]
    assert [s.short_label for s in first] == [f'{a.short_label}-1', f'{b.short_label}-1']

    again, = col.split_samples(a)
    assert again.short_label == f'{a.short_label}-2'
    assert again.id in {s.id for s in col.get_samples(per_page=None)}


def test_the_local_split_is_an_unsaved_copy_that_saves_unlinked(instance_with_collection):
    """Documents the server: POST /api/v1/samples takes no parent_id, so only reactions and
    wellplates turn a local split into a linked subsample. split_samples() is the linked way."""
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCCC')
    sample.save()
    sub = sample.split()
    assert sub.id is None and sub.json_data['parent_id'] == sample.id
    sub.save()
    assert instance_with_collection['instance'].get_sample(sub.id).json_data.get('parent_id') is None
