"""Literature references on a live ELN (M2.6). The DOI lookup needs doi.org and is skipped offline."""
import uuid

import pytest

pytestmark = pytest.mark.integration


def test_cite_retype_list_and_remove(instance_with_collection):
    col = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.save()
    title = f'API_TEST paper {uuid.uuid4().hex[:6]}'

    (ref,) = sample.add_reference(doi='10.9999/api-test', title=title)
    assert (ref.title, ref.litype) == (title, 'citedOwn')
    (ref,) = sample.set_reference_type(ref, 'citedRef')
    assert ref.litype == 'citedRef'

    reaction = col.new_reaction()
    reaction.save()
    reaction.add_reference(url='https://example.org/api-test', title='web page')
    overview = col.references()
    assert [r.title for r in overview['sample']] == [title]
    assert [r.title for r in overview['reaction']] == ['web page']

    sample.remove_reference(ref)
    assert sample.references() == []


@pytest.mark.parametrize('make', ['new_wellplate', 'new_research_plan', 'new_screen'])
def test_other_element_types_take_references(instance_with_collection, make):
    element = getattr(instance_with_collection['main_collection'], make)()
    element.save()
    assert [r.title for r in element.add_reference(title='a book', isbn='978-3-16-148410-0')] == ['a book']


def test_doi_metadata(logged_in_instance):
    try:
        meta = logged_in_instance.doi_metadata('10.1021/ja00051a040')
    except Exception as e:  # noqa: BLE001 - doi.org unreachable from this stack
        pytest.skip(f'doi.org not reachable: {e}')
    assert '@' in meta['bibtex'] and isinstance(meta['BTjson'], (dict, list))
