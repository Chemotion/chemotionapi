"""Cell lines offline, on payloads captured from ELN v4.0.1."""
import json
import os
from types import SimpleNamespace

import pytest

from chemotion_api.elements import CellLine
from chemotion_api.elements.abstract_element import AbstractElement

SESSION = SimpleNamespace(_host_url='http://localhost',
                          schema_manager=SimpleNamespace(generate_model_type=lambda *a: 'chemotion:type'))
SEGMENTS = SimpleNamespace(all_classes=[])
FIXTURES = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'cell_line')


def _line(name='cellline_show.json'):
    with open(os.path.join(FIXTURES, name)) as f:
        data = json.load(f)
    if 'cell_lines' in data:
        data = data['cell_lines'][0]
    line = CellLine(SEGMENTS, SESSION, json_data=data)
    line._data_loaded = True
    return line


def test_routing_and_unwrapped_records():
    line = _line()
    assert AbstractElement.get_url('cell_line') == '/api/v1/cell_lines'
    assert line.save_url() == '/api/v1/cell_lines'
    assert line._record_from_detail({'id': 1}) == {'id': 1}


def test_sample_and_material_fields_are_apart():
    line = _line()
    assert set(line.properties.keys()) == {'name', 'description', 'amount', 'unit', 'passage', 'contamination'}
    assert line.material['organism'] == 'Homo sapiens'
    assert line.material['source'] == 'ATCC'


def test_a_save_sends_the_whole_material_and_the_id_in_the_body():
    out = _line()._clean_properties_data()
    assert out['cell_line_sample_id'] == str(_line().id)
    assert out['material_names'].startswith('API-HeLa-') and out['source'] == 'ATCC'
    assert out['organism'] == 'Homo sapiens' and 'material_description' in out


def test_writes_are_validated():
    from pydantic import ValidationError
    line = _line()
    with pytest.raises(ValidationError):
        line.properties['passage'] = 'third'
    with pytest.raises(ValidationError):
        line.material['optimal_growth_temp'] = 'warm'
    line.material['optimal_growth_temp'] = '37'
    assert line.material['optimal_growth_temp'] == 37.0


def test_editing_someone_elses_material_is_refused_before_saving(monkeypatch):
    line = _line()
    line._material_owner = 99
    monkeypatch.setattr(line, '_session', SimpleNamespace(current_user_id=lambda: 7))
    line.material['tissue'] = 'liver'
    with pytest.raises(PermissionError, match="created by another user"):
        line.save()


def test_the_current_user_is_fetched_once_per_login(monkeypatch):
    """The owner check ran `User.load_me` on every save that changed a material field."""
    from chemotion_api.connection import Connection
    calls = []
    monkeypatch.setattr('chemotion_api.user.User.load_me',
                        classmethod(lambda cls, s: calls.append(1) or SimpleNamespace(id=7)))
    con = Connection('https://eln.example.org')
    assert [con.current_user_id() for _ in range(3)] == [7, 7, 7] and len(calls) == 1
    con.set_bearer_token('another-login')
    con.current_user_id()
    assert len(calls) == 2, 'a new login may be another user'


def test_required_fields_are_checked_before_saving():
    line = _line()
    line.properties['amount'] = None
    with pytest.raises(ValueError, match="amount"):
        line.save()
