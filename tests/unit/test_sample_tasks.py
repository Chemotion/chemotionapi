"""Sample (weighing) tasks (M5.5), offline."""
import pytest

from chemotion_api.sample_tasks import SampleTask, create_sample_task, sample_tasks

TASK = {'id': 4, 'description': 'weigh it', 'sample_id': 3, 'required_scan_results': 2, 'done': False,
        'result_value': None, 'result_unit': 'g', 'scan_results': []}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params')), sorted(kw.get('files') or {})))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def put(self, url, **kw):
        return self._call('put', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def test_task_lifecycle(tmp_path):
    scan = tmp_path / 'scale.png'
    scan.write_bytes(b'\x89PNG')
    done = dict(TASK, done=True, result_value=1.6)
    session = _Session(_Res(201, TASK), _Res(201, {'id': 1, 'measurement_value': 1.5}), _Res(200, done),
                       _Res(200, [done]), _Res(200, {'deleted': 4}))
    task = create_sample_task(session, type('S', (), {'id': 3})(), 'weigh it', 2)
    assert (task.id, task.required_scan_results) == (4, 2)
    task.add_scan_result(str(scan), 1.5, 'g')
    assert task.update(description='weigh twice').done
    assert sample_tasks(session, 'done')[0].result_value == 1.6
    task.delete()
    assert session.calls[0][2] == {'required_scan_results': 2, 'description': 'weigh it', 'sample_id': 3}
    assert session.calls[1][1:] == ('/api/v1/sample_tasks/4/scan_results',
                                    {'measurement_value': 1.5, 'measurement_unit': 'g'}, ['file'])
    assert session.calls[3][2] == {'status': 'done'}


def test_disabled_feature_and_refusals():
    with pytest.raises(ConnectionError, match='not enabled'):
        sample_tasks(_Session(_Res(404, {})))
    with pytest.raises(ValueError, match='status'):
        sample_tasks(_Session(), 'closed')
    with pytest.raises(ValueError, match='only open tasks'):
        SampleTask.from_json(TASK, _Session(_Res(400, {}))).delete()
