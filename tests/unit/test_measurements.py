"""Measurements (M5.2), offline."""
import pytest

from chemotion_api.measurements import MeasurementError, create_measurements, load_measurements


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text, self.content = status, payload, str(payload), b'x'

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, **kw):
        self.calls.append(('get', url, params))
        return self.responses.pop(0)

    def post(self, url, data=None, **kw):
        self.calls.append(('post', url, data))
        return self.responses.pop(0)


class _El:
    def __init__(self, kind, eid, short_label=None):
        self.element_type, self.id, self.short_label = kind, eid, short_label


def test_load_flattens_the_sample_hierarchy():
    payload = {'measurements': [
        {'id': 3, 'short_label': 'API-1', 'measurements': [{'id': 1, 'description': 'yield', 'value': 87.5,
                                                            'unit': '%', 'source_type': 'research_plan', 'source_id': 9}]},
        {'id': 4, 'short_label': 'API-1-1', 'measurements': [{'id': 2, 'description': 'mp', 'value': 120.0,
                                                              'unit': 'C', 'source_type': 'research_plan', 'source_id': 9}]}]}
    session = _Session(_Res(200, payload))
    found = load_measurements(session, 3, source=_El('research_plan', 9))
    assert [(m.id, m.sample_id, m.sample_short_label) for m in found] == [(1, 3, 'API-1'), (2, 4, 'API-1-1')]
    assert session.calls[0][2] == {'sample_id': 3, 'show_hierarchy': True, 'source_type': 'research_plan',
                                   'source_id': 9}


def test_create_sends_short_labels_and_reports_refused_rows():
    ok = {'description': 'yield', 'sample_identifier': 'API-1', 'errors': [], 'id': 5}
    bad = {'description': 'x', 'sample_identifier': 'NOPE', 'errors': ['Could not find sample']}
    session = _Session(_Res(201, {'measurements': [ok]}), _Res(201, {'measurements': [ok, bad]}))
    plan = _El('research_plan', 9)
    assert create_measurements(session, plan, [{'sample': _El('sample', 1, 'API-1'), 'description': 'yield',
                                                'value': '87.5', 'unit': '%'}]) == [ok]
    body = session.calls[0][2]
    assert (body['source_type'], body['source_id']) == ('research_plan', 9)
    assert body['raw_data'][0]['sample_identifier'] == 'API-1' and body['raw_data'][0]['value'] == 87.5
    with pytest.raises(MeasurementError, match='1 of 2') as err:
        create_measurements(session, plan, [{'sample': 'API-1', 'description': 'yield', 'value': 1, 'unit': '%'},
                                            {'sample': 'NOPE', 'description': 'x', 'value': 1, 'unit': '%'}])
    assert err.value.results[1]['errors'] == ['Could not find sample']
    with pytest.raises(ValueError, match='needs sample'):
        create_measurements(session, plan, [{'sample': 'API-1', 'value': 1}])
