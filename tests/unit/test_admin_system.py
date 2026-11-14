"""System administration (M7.6), offline."""
import pytest

from chemotion_api.user import Admin


class _Res:
    def __init__(self, status, payload=None, text=''):
        self.status_code, self._payload, self.text, self.content = status, payload, text, b''

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get_json_session_header(self):
        return {'Content-Type': 'application/json'}

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params'))))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def put(self, url, **kw):
        return self._call('put', url, kw)


def _admin(session):
    admin = Admin.__new__(Admin)
    admin._session = session
    return admin


def test_job_restart_and_tasks_are_explicit():
    session = _Session(_Res(200, {}), _Res(204), _Res(500, text='ActiveRecord::RecordNotFound'))
    adm = _admin(session)
    adm.restart_job({'id': 7})
    adm.queue_admin_task('rerender_reactions')
    assert session.calls[:2] == [('put', '/api/v1/admin/jobs/restart', {'id': 7}),
                                 ('get', '/api/v1/admin/jobs/queue_task', {'task': 'rerender_reactions'})]
    with pytest.raises(LookupError):
        adm.restart_job(8)
    for bad in (None, 'all', [1, 2]):
        with pytest.raises(ValueError):
            adm.restart_job(bad)
    with pytest.raises(ValueError):
        adm.queue_admin_task('reset_db')


def test_matrix_update_needs_fields():
    session = _Session(_Res(201))
    adm = _admin(session)
    with pytest.raises(ValueError):
        adm.update_matrix(2)
    adm.update_matrix({'id': 2}, enabled=True)
    assert session.calls == [('put', '/api/v1/admin/matrix', {'id': 2, 'enabled': True})]
