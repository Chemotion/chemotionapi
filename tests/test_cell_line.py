"""Cell lines on a live ELN (M4.1)."""
import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def cell_line(instance_with_collection):
    col = instance_with_collection['main_collection']
    cl = col.new_cell_line()
    cl.properties.update(material_names=f'API line {uuid.uuid4().hex[:6]}', source='ATCC', amount=1000,
                         unit='cell count', passage=3, organism='Homo sapiens', name='batch 1')
    cl.save()
    return instance_with_collection['instance'], col, cl


def test_create_load_update(cell_line):
    instance, col, cl = cell_line
    assert cl.id and cl.material_id and cl.short_label.startswith('API-C')
    loaded = instance.get_cell_line(cl.id)
    assert (loaded.properties['name'], loaded.properties['organism']) == ('batch 1', 'Homo sapiens')
    loaded.properties['passage'] = 4
    loaded.properties['contamination'] = 'mycoplasma-free'
    loaded.analyses.add_analyses('growth curve')
    loaded.save()
    again = instance.get_cell_line(cl.id)
    assert (again.properties['passage'], again.properties['contamination']) == (4, 'mycoplasma-free')
    assert [a['name'] for a in again.analyses] == ['growth curve']
    assert cl.properties['material_names'] in {m['name'] for m in instance.cell_line_materials()}
    assert [c.id for c in col.get_cell_lines()] == [cl.id]


def test_copy_split_move_delete(cell_line, instance_with_collection):
    instance, col, cl = cell_line
    copied, split = cl.copy(col), cl.split(col)
    assert copied.material_id == split.material_id == cl.material_id
    assert split.short_label == f'{cl.short_label}-1'
    root = instance.get_root_collection()
    root.add_collection(instance_with_collection['name'] + '_other')
    root.save()
    other = root.get_collection(instance_with_collection['name'] + '_other')
    col.assign_elements(other, copied)
    assert [c.id for c in other.get_cell_lines()] == [copied.id]
    assert copied.delete()
    assert {c.id for c in col.get_cell_lines(per_page=50)} == {cl.id, split.id}
