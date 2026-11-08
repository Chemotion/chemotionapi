"""User administration (M7.4), offline: guards and request shapes."""
import pytest

from chemotion_api.user import Admin, Group


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text, self.content = status, payload, str(payload), b'x'

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

    def put(self, url, **kw):
        return self._call('put', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def _admin(session):
    admin = Admin.__new__(Admin)
    admin._session = session
    return admin


def test_delete_user_needs_the_abbreviation():
    session = _Session(_Res(200, {'id': 18, 'initials': 'ABC'}), _Res(200, {'id': 18, 'initials': 'ABC'}), _Res(204))
    adm = _admin(session)
    with pytest.raises(ValueError, match="confirm='ABC'"):
        adm.delete_user(18, confirm='abc')
    adm.delete_user(18, confirm='ABC')
    assert [c[:2] for c in session.calls] == [('get', '/api/v1/admin/users/18'), ('get', '/api/v1/admin/users/18'),
                                              ('delete', '/api/v1/admin/users/18')]


def test_update_rights_and_password_requests():
    session = _Session(_Res(200, {'id': 18}), _Res(200, {'id': 18}), _Res(200, {'pwd': 'xyz12345'}))
    adm = _admin(session)
    adm.update_user(18, first_name='A', account_active=False)
    adm.set_user_rights(18, molecule_editor=True, generic_elements_admin=False)
    assert adm.reset_password(18) == 'xyz12345'
    assert session.calls[0][2] == {'first_name': 'A', 'account_active': False}
    assert session.calls[1][2] == {'molecule_editor': True, 'auth_generic_admin': {'elements': False}}
    assert session.calls[2] == ('put', '/api/v1/admin/users/18/resetPassword', {'random': True})
    with pytest.raises(ValueError, match='Unknown user fields'):
        adm.update_user(18, admin=True)
    with pytest.raises(ValueError, match='8 characters'):
        adm.reset_password(18, 'short')
    with pytest.raises(ValueError, match='Name the rights'):
        adm.set_user_rights(18)


def test_group_actions():
    session = _Session(_Res(200, {'root': {}}), _Res(200, {'destroyed_id': 4}), _Res(422, 'Cannot remove the last admin'))
    adm = _admin(session)
    group = Group.__new__(Group)
    group.id, group.name_abbreviation = 4, 'GRP'
    adm.remove_users_from_group(group, 7)
    adm.delete_group(group, confirm='GRP')
    assert session.calls[0][2] == {'action': 'NodeDel', 'rootType': 'Group', 'id': 4, 'actionType': 'Person',
                                   'rm_users': [7]}
    assert session.calls[1][2] == {'action': 'RootDel', 'rootType': 'Group', 'id': 4, 'destroy_obj': True}
    with pytest.raises(ValueError, match='last admin'):
        adm.set_group_admin(group, 7, admin=False)
