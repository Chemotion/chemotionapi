"""Comments on a live ELN (M1.3)."""
import pytest

from chemotion_api.connection import ChemotionRequestError

pytestmark = pytest.mark.integration


@pytest.fixture()
def sample(instance_with_collection):
    s = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    s.save()
    return s


def test_comment_on_the_element_and_on_a_section(sample):
    whole = sample.add_comment('Looks off')
    nmr = sample.add_comment('Check the NMR', section='analyses')
    assert (whole.section, nmr.section) == ('sample_header', 'sample_analyses')
    assert {c.id for c in sample.comments()} == {whole.id, nmr.id}


def test_edit_resolve_and_delete(sample):
    comment = sample.add_comment('Check the NMR')
    comment.update('Check the 1H NMR')
    assert sample.comments()[0].content == 'Check the 1H NMR'

    comment.resolve()
    assert comment.is_resolved
    with pytest.raises(ChemotionRequestError, match='422'):
        comment.update('too late')

    comment.delete()
    assert sample.comments() == []


@pytest.mark.parametrize('make', ['new_reaction', 'new_wellplate', 'new_research_plan', 'new_screen'])
def test_every_commentable_element_type(instance_with_collection, make):
    element = getattr(instance_with_collection['main_collection'], make)()
    element.save()
    comment = element.add_comment('hi', section='properties')
    assert comment.section.endswith(('_properties', '_research_plan'))
    assert [c.id for c in element.comments()] == [comment.id]


def test_an_unsaved_element_is_refused(instance_with_collection):
    with pytest.raises(ValueError, match='Save the sample'):
        instance_with_collection['main_collection'].new_sample_smiles('CO').add_comment('x')
