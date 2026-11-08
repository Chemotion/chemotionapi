"""NMR simulation, predictions and compute tasks (M5.4), offline."""
import pytest

from chemotion_api.compute import ComputeTask, compute_tasks, predict_products, simulate_nmr, submit_compute_task

TASK = {'id': 24, 'sample_id': 3, 'status': 'completed', 'homo': -5.14, 'lumo': -3.63, 'tddft': {'s1_energy': 1.3},
        'task_id': 'abc', 'data': {'raw': 'log'}}


class _Res:
    def __init__(self, status, payload=None, text=None):
        self.status_code, self._payload = status, payload
        self.text = text if text is not None else str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params'))))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def test_tasks_check_revoke_delete():
    session = _Session(_Res(200, {'compute_tasks': [TASK]}), _Res(200, {'check': dict(TASK, status='success')}),
                       _Res(200, {'revoke': dict(TASK, status='revoked')}), _Res(200, TASK))
    (task,) = compute_tasks(session)
    assert task.results['homo'] == -5.14 and 'task_id' not in task.results
    assert task.check().status == 'success'
    assert task.revoke().status == 'revoked'
    task.delete()
    assert [c[1] for c in session.calls[1:]] == ['/api/v1/compute_tasks/24/check', '/api/v1/compute_tasks/24/revoke',
                                                  '/api/v1/compute_tasks/24']


def test_no_compute_server_and_no_permission():
    with pytest.raises(ConnectionError, match='compute server'):
        ComputeTask.from_json(TASK, _Session(_Res(500, {}))).check()
    sample = type('S', (), {'id': 3})()
    with pytest.raises(PermissionError, match='does not run computations'):
        submit_compute_task(_Session(_Res(200, {'error': 'Unauthorized'}, text='{"error":"Unauthorized"}')), sample)


def test_submit_returns_the_samples_newest_task():
    sample = type('S', (), {'id': 3})()
    session = _Session(_Res(201, None, text=''), _Res(200, {'compute_tasks': [dict(TASK, id=25, status='pending'), TASK]}))
    assert submit_compute_task(session, sample).id == 25
    assert session.calls[0] == ('post', '/api/v1/molecules/compute', {'sampleId': 3})


def test_predictions_and_simulation():
    session = _Session(_Res(201, [{'products': ['CC=O']}]), _Res(201, {'error': 'Prediction Sever not found.'}),
                       _Res(500, None, text='<html>'), _Res(200, {'response_1h': 'x', 'response_13c': 'y'}))
    assert predict_products(session, ['CCO']) == [{'products': ['CC=O']}]
    assert session.calls[0] == ('post', '/api/v1/prediction/products', {'smis': ['CCO']})
    with pytest.raises(ConnectionError, match='Sever not found'):
        predict_products(session, ['CCO'])
    with pytest.raises(ConnectionError, match='always fails'):
        predict_products(session, ['CCO'])
    assert simulate_nmr(session, 7) == {'response_1h': 'x', 'response_13c': 'y'}
    with pytest.raises(ValueError):
        predict_products(session, [])
