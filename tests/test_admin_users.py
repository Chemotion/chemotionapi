"""User administration on a live ELN (M7.4)."""
import random
import string

import pytest

from chemotion_api import Instance

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin(config_login):
    instance = Instance(config_login['ELN_URL']).login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS'])
    return instance, instance.get_user()


@pytest.fixture()
def person(admin):
    _, adm = admin
    abbr = ''.join(random.choices(string.ascii_uppercase, k=4))
    created = adm.create_person(first_name='Temp', last_name=f'User{abbr}', name_abbreviation=abbr,
                                password='QWEasd123!"§', email=f'{abbr.lower()}@temp.example')
    return created, abbr


def test_find_update_reset_rights(config_login, admin, person):
    _, adm = admin
    user, abbr = person
    assert [u['id'] for u in adm.find_users(f'User{abbr}')] == [user.id]
    assert adm.update_user(user, first_name='Tempo')['first_name'] == 'Tempo'
    password = adm.reset_password(user)
    Instance(config_login['ELN_URL']).login(abbr, password)
    adm.set_user_rights(user, converter_admin=True, generic_segments_admin=True)
    assert adm.two_factor_enable_link(user).startswith('http')
    adm.disable_two_factor(user)
    assert isinstance(adm.default_allocated_space(), int)


def test_delete_and_restore(admin, person):
    _, adm = admin
    user, abbr = person
    with pytest.raises(ValueError, match='pass confirm'):
        adm.delete_user(user, confirm='WRONG')
    adm.delete_user(user, confirm=abbr)
    assert adm.find_users(f'User{abbr}') == []
    assert adm.restore_user(abbr)['status'] == 'success'
    assert [u['id'] for u in adm.find_users(f'User{abbr}')] == [user.id]
    with pytest.raises(LookupError):
        adm.restore_user('NO-SUCH-USER')


def test_group_membership_and_deletion(admin, person):
    instance, adm = admin
    user, abbr = person
    group = adm.create_group('API test', f'Group {abbr}', f'G{abbr}')
    instance.device_manager.add_users_to_group_by_id(group, user.id)
    adm.remove_users_from_group(group, user)
    with pytest.raises(ValueError, match='pass a loaded one and confirm'):
        adm.delete_group(group, confirm='nope')
    adm.delete_group(group, confirm=group.name_abbreviation)
    assert f'G{abbr}' not in {g.name_abbreviation for g in adm.fetchGroups()}
