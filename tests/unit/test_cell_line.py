"""Cell lines (M4.1), offline, against a real ELN `main` cell line payload."""
import copy
import json
import os

import pytest

from chemotion_api.elements.cell_line import CellLine
from chemotion_api.elements.registry import element_type_info
from chemotion_api.schema_manager import SchemaManager

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'cell_line_v4_main.json')


class _About:
    status_code, text = 200, '<h4>Version: v4.0.0</h4>'


class _Res:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    schema_manager = SchemaManager(_About())
    _host_url = 'http://eln.test'

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.records = {r._payload['id']: r._payload for r in responses}

    def get(self, url, **kw):
        # The cell line route answers unwrapped; serve what was last returned for that id.
        wanted = int(url.removesuffix('.json').rsplit('/', 1)[-1])
        return _Res(200, self.records.get(wanted, _payload()))

    def post(self, url, data=None, **kw):
        self.calls.append(('post', url, data))
        return self.responses.pop(0)

    def put(self, url, data=None, **kw):
        self.calls.append(('put', url, json.loads(data)))
        return self.responses.pop(0)


class _Segments:
    all_classes = []


def _payload():
    with open(FIXTURE) as f:
        return json.load(f)


def _cell_line(session=None, payload=None):
    return CellLine(_Segments(), session or _Session(), json_data=payload or _payload())


def test_registered():
    info = element_type_info('cell_line')
    assert (info.cls, info.url) == (CellLine, '/api/v1/cell_lines')


def test_properties_merge_sample_and_material():
    cl = _cell_line()
    p = cl.properties
    assert (p['name'], p['amount'], p['unit'], p['passage']) == ('batch 1', 1000, 'cell count', 4)
    assert (p['material_names'], p['source'], p['organism']) == ('HeLa', 'ATCC', 'Homo sapiens')
    assert cl.material_id == 1 and cl.attachments is None


def test_update_puts_to_the_collection_url_with_the_id_in_the_body():
    session = _Session(_Res(200, _payload()))
    cl = _cell_line(session)
    cl.properties['passage'] = 5
    cl.save()
    (method, url, body), = session.calls
    assert (method, url) == ('put', '/api/v1/cell_lines')
    assert body['cell_line_sample_id'] == str(cl.id) and body['passage'] == 5
    assert body['material_names'] == 'HeLa' and 'container' in body
    assert 'cellline_material' not in body and 'id' not in body


def test_a_new_cell_line_needs_material_and_amounts():
    payload = copy.deepcopy(_payload())
    for key in ('id', 'cellline_material'):
        payload.pop(key)
    cl = _cell_line(payload=payload)
    assert cl.is_new
    with pytest.raises(ValueError, match='material_names'):
        cl.clean_data()


def test_copy_and_split():
    session = _Session(_Res(201, dict(_payload(), id=8, short_label='API-C2')),
                       _Res(201, dict(_payload(), id=9, short_label='API-C1-1')))
    cl = _cell_line(session)
    col = type('C', (), {'id': 4, 'label': 'x'})()
    assert cl.copy(col).short_label == 'API-C2'
    assert cl.split(col).id == 9
    assert [(c[1], c[2]['id'], c[2]['collection_id']) for c in session.calls] == [
        ('/api/v1/cell_lines/copy', cl.id, 4), ('/api/v1/cell_lines/split', cl.id, 4)]
    assert session.calls[0][2]['container']['container_type'] == 'root'
