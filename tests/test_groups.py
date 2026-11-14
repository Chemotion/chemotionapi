"""Group lifecycle against a live ELN v4: create → add → promote → demote → remove → delete.

ELN v4.0.0 moved every group operation to new routes; these were verified once by hand on
2026-11-11 and are user-facing (docs/Examples.rst, Example 2), so the suite covers them now.
Membership is read back from the server's own listing, not from the client object.
"""
import random
import string

import pytest

from chemotion_api import Instance


def _abbr():
    return 'G' + ''.join(random.choices(string.ascii_uppercase, k=3))


def _server_group(instance: Instance, group_id: int) -> dict | None:
    groups = instance._con.get('/api/v1/groups').json().get('currentGroups', [])
    return next((g for g in groups if g['id'] == group_id), None)


def test_group_lifecycle(logged_in_instance: Instance):
    me = logged_in_instance.get_user()
    mm = next(u for u in logged_in_instance.find_user_by_name('Max Mustermann')
              if u.name_abbreviation == 'MM')

    group = me.create_group('API', f'Test {_abbr()}', _abbr())
    try:
        listed = _server_group(logged_in_instance, group.id)
        assert listed is not None
        assert [u['id'] for u in listed['users']] == [me.id]
        assert [u['id'] for u in listed['admins']] == [me.id]

        group.add_users(mm)
        assert {u['id'] for u in _server_group(logged_in_instance, group.id)['users']} == {me.id, mm.id}

        group.promote_admin(mm.id)
        assert {u['id'] for u in _server_group(logged_in_instance, group.id)['admins']} == {me.id, mm.id}

        group.demote_admin(mm.id)
        assert {u['id'] for u in _server_group(logged_in_instance, group.id)['admins']} == {me.id}

        with pytest.raises(ValueError):
            group.demote_admin(me.id)       # the last admin cannot be removed

        group.remove_users(mm)
        assert [u['id'] for u in _server_group(logged_in_instance, group.id)['users']] == [me.id]
    finally:
        group.delete()
    assert _server_group(logged_in_instance, group.id) is None
