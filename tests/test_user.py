import random
import string

import pytest

from chemotion_api import Instance
def random_char(y):
    return ''.join(random.choice(string.ascii_letters) for x in range(y))

def test_login_sucess(config_login):
    Instance(config_login.get('ELN_URL')).test_connection().login(config_login.get('ELN_USER'), config_login.get('ELN_PASS'))
    assert True

def test_login_fails(config_login):
    with pytest.raises(PermissionError):
        Instance(config_login.get('ELN_URL')).test_connection().login(config_login.get('ELN_USER'), 'ELN_PASS')

def test_get_user_not_logged_in(config_login):
    with pytest.raises(PermissionError):
        Instance(config_login.get('ELN_URL')).test_connection().get_user()

def test_wrong_instance_login(config_login):
    with pytest.raises(Exception):
        Instance('https://google.de').login(config_login.get('ELN_USER'), config_login.get('ELN_PASS'))
    with pytest.raises(Exception):
        Instance('https://google.de').get_user()

def test_get_user(config_login):
    instance = Instance(config_login.get('ELN_URL')).test_connection().login(config_login.get('ELN_USER'), config_login.get('ELN_PASS'))
    user = instance.get_user()
    assert user.email == 'api@kit.edu'
    with pytest.raises(Exception):
        user.fetchDevices()
    name_abbreviation = random_char(3)
    with pytest.raises(Exception):
        instance.device_manager.create_new_device('Fist_name', 'Last_Name', name_abbreviation)
def test_get_admin_devices(config_login):
    user = Instance(config_login.get('ELN_URL')).test_connection().login(config_login.get('ELN_ADMIN_USER'), config_login.get('ELN_ADMIN_PASS')).get_user()
    user.fetchDevices()
    devices = user.devices
    assert len(devices) >= 2
    assert len(devices[0].get_jwt()) >= 100
    super_devices = [d for d in devices if d.is_super_device]
    assert len(super_devices) > 0
    jwt = super_devices[0].get_jwt()
    instance_device = Instance(config_login.get('ELN_URL')).test_connection().login_token(jwt)
    d_user = instance_device.get_user()
    assert d_user.id == 6
    d_5_d_user_jwt = instance_device.device_manager.get_jwt_for_device(5)
    assert len(d_5_d_user_jwt) >= 100
    instance_device_d4 = Instance(config_login.get('ELN_URL')).test_connection().login_token(d_5_d_user_jwt)
    with pytest.raises(Exception):
        instance_device_d4.device_manager.get_jwt_for_device(6)

def test_create_devices(config_login):
    instance = Instance(config_login.get('ELN_URL')).test_connection().login(config_login.get('ELN_ADMIN_USER'), config_login.get('ELN_ADMIN_PASS'))

    name_abbreviation = random_char(3)
    res = instance.device_manager.create_new_device('Fist_name', 'Last_Name', name_abbreviation)
    with pytest.raises(Exception):
        instance.device_manager.create_new_device('Fist_name', 'Last_Name', name_abbreviation)
    assert res.name_abbreviation == name_abbreviation
    res.delete()
