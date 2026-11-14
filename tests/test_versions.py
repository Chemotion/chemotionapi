"""Version history and revert on a live ELN (M1.5)."""
import pytest

pytestmark = pytest.mark.integration


def test_history_and_reverting_one_field(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.properties['name'] = 'one'
    sample.save()
    sample = instance.get_sample(sample.id)
    sample.properties['name'] = 'two'
    sample.properties['description'] = 'changed too'
    sample.save()

    latest = sample.versions()[0]
    change = next(c for c in latest.changes if c.klass_name == 'Sample')
    assert (change.fields['name'].old_value, change.fields['name'].new_value) == ('one', 'two')

    latest.revert(fields=['name'])
    sample = instance.get_sample(sample.id)
    assert sample.properties['name'] == 'one'
    assert sample.properties['description'] == 'changed too'
    assert len(sample.versions()) == 3  # the revert is a change of its own


@pytest.mark.parametrize('make', ['new_reaction', 'new_wellplate', 'new_research_plan', 'new_screen'])
def test_every_versioned_type_reports_a_rename(instance_with_collection, make):
    element = getattr(instance_with_collection['main_collection'], make)()
    element.save()
    element.name = 'renamed'
    element.save()
    names = [c.fields['name'].new_value for v in element.versions() for c in v.changes if 'name' in c.fields]
    assert 'renamed' in names


def test_generic_elements_are_refused(instance_with_collection):
    element = instance_with_collection['main_collection'].new_generic('try')
    element.save()
    with pytest.raises(ValueError, match='no version history'):
        element.versions()
