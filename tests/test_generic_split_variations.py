"""Splitting generic elements and their variations on a live ELN (M6.4)."""
import pytest

from chemotion_api.elements.generic_element import variation_key

pytestmark = pytest.mark.integration


def test_split(instance_with_collection):
    col = instance_with_collection['main_collection']
    element = col.new_generic('wrk')
    element.name = 'split me'
    element.save()
    (child,) = col.split_generic_elements(element)
    assert child.short_label == f'{element.short_label}-1' and child.name == 'split me'
    assert {e.id for e in col.get_generics_by_name('wrk', per_page=None)} == {element.id, child.id}


def test_variations_round_trip(instance_with_collection, tmp_path):
    element = instance_with_collection['main_collection'].new_generic('wrk')
    element.save()
    assert element.variations() == {'variations': {}, 'layout': {}}
    key = variation_key('general', 'temperature')
    rows = {'row-1': {'properties': {key: {'value': 20, 'unit': 'C'}}, 'metadata': {'notes': 'first'}, 'segments': {}}}
    saved = element.save_variations(rows, layout={'selected': [key]})
    assert saved['layout'] == {'selected': [key]} and set(saved['variations']) == {'row-1'}
    assert element.variations()['variations']['row-1']['metadata'] == {'notes': 'first'}

    workbook = element.export_variations(str(tmp_path / 'variations.xlsx'))
    assert isinstance(element.import_variations(workbook), list)
    with pytest.raises(ValueError):
        bad = tmp_path / 'bad.txt'
        bad.write_text('x')
        element.import_variations(str(bad))
