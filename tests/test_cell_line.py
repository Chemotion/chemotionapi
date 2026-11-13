"""Cell lines against a live ELN v4.0.1: create, reload, edit sample and material, re-link."""
import uuid

from chemotion_api.collection import Collection
from chemotion_api.elements import CellLine


def test_cell_line_round_trip(instance_with_collection: dict):
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    material = f'API-line-{uuid.uuid4().hex[:6]}'
    line = col.new_cell_line(material, source='ATCC')
    line.properties['amount'] = 1000
    line.properties['unit'] = 'cells'
    line.properties['passage'] = 3
    line.material['organism'] = 'Homo sapiens'
    line.save()

    loaded = instance.get_cell_line(line.id)
    assert isinstance(loaded, CellLine)
    assert (loaded.properties['amount'], loaded.properties['passage']) == (1000, 3)
    assert loaded.material['name'] == material and loaded.material['organism'] == 'Homo sapiens'

    listed = next(c for c in col.get_cell_lines() if c.id == line.id)
    listed.properties['passage'] = 4
    listed.material['tissue'] = 'cervix'          # our own material: the server applies it
    listed.save()
    again = instance.get_cell_line(line.id)
    assert again.properties['passage'] == 4
    assert again.material['tissue'] == 'cervix'
    assert again.material['name'] == material     # not re-linked by a sample-only edit

    other = f'API-line-{uuid.uuid4().hex[:6]}'
    again.material['name'] = other                 # re-link to another material
    again.save()
    assert instance.get_cell_line(line.id).material['name'] == other
