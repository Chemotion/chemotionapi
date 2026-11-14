"""Private notes on a live ELN (M1.4)."""
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('make', ['new_reaction', 'new_wellplate', 'new_research_plan', 'new_screen'])
def test_write_replace_and_delete(instance_with_collection, make):
    element = getattr(instance_with_collection['main_collection'], make)()
    element.save()
    assert element.private_note() is None

    element.set_private_note('first')
    assert element.private_note() == 'first'
    element.set_private_note('second')
    assert element.private_note() == 'second'

    assert element.delete_private_note() is True
    assert element.private_note() is None
    assert element.delete_private_note() is False


def test_a_sample_note(instance_with_collection):
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.save()
    sample.set_private_note('weighed twice')
    assert instance_with_collection['instance'].get_sample(sample.id).private_note() == 'weighed twice'


def test_an_unsaved_element_is_refused(instance_with_collection):
    with pytest.raises(ValueError, match='Save the sample'):
        instance_with_collection['main_collection'].new_sample_smiles('CO').private_note()
