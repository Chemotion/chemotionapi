"""Finding samples and reactions by short label on a live ELN (M1.2)."""
import pytest

pytestmark = pytest.mark.integration


def test_find_a_sample_and_a_reaction(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.save()
    reaction = col.new_reaction()
    reaction.save()
    sample.load()
    reaction.load()

    found = instance.find_sample_by_short_label(sample.short_label)
    assert found is not None and found.id == sample.id
    found = instance.find_reaction_by_short_label(reaction.short_label)
    assert found is not None and found.id == reaction.id


def test_an_unknown_label_is_none(logged_in_instance):
    assert logged_in_instance.find_sample_by_short_label('NOPE-999999') is None
    assert logged_in_instance.find_reaction_by_short_label('NOPE-R999999') is None
