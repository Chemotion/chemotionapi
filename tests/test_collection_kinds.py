"""Collection membership for the element kinds beyond sample/reaction/research plan, live on ELN v4.

Each kind is assigned to a second collection and then removed from the first; the server must show
it in exactly the destination afterwards.
"""
import uuid

import pytest


@pytest.fixture()
def two_collections(logged_in_instance):
    root = logged_in_instance.get_root_collection()
    a, b = (f'API_TEST_kinds_{x}_{uuid.uuid4().hex[:6]}' for x in 'ab')
    root.add_collection(a)
    root.add_collection(b)
    root.save()
    root = logged_in_instance.get_root_collection(reload=True)
    return logged_in_instance, root.get_collection(a), root.get_collection(b)


def _cell_line(instance, col):
    line = col.new_cell_line(f'API-kind-{uuid.uuid4().hex[:6]}', source='ATCC')
    line.properties.update({'amount': 1, 'unit': 'cells', 'passage': 1})
    return line


def _device(instance, col):
    res = instance._con.post('/api/v1/device_descriptions', data={'collection_id': col.id, 'name': 'kind test'})
    device_id = res.json()['device_description']['id']
    return next(d for d in col.get_device_descriptions() if d.id == device_id)


@pytest.mark.parametrize("make, listing", [
    (lambda inst, col: col.new_wellplate(), lambda col: col.get_wellplates()),
    (lambda inst, col: col.new_screen(), lambda col: col.get_screens()),
    (_device, lambda col: col.get_device_descriptions()),
    (lambda inst, col: col.new_generic('wrk'), lambda col: col.get_generics_by_name('wrk')),
    (_cell_line, lambda col: col.get_cell_lines()),
    (lambda inst, col: col.new_sbmm_sample(uniprot='P69905'), lambda col: col.get_sbmm_samples()),
], ids=['wellplate', 'screen', 'device_description', 'generic', 'cell_line', 'sbmm_sample'])
def test_move_element_kind(two_collections, make, listing):
    instance, src, dst = two_collections
    element = make(instance, src)
    if element.is_new:
        element.save()
    locked = src.move_elements(dst, element)
    assert locked == []
    assert any(e.id == element.id for e in listing(dst))
    assert not any(e.id == element.id for e in listing(src))
