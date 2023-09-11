import pytest

from chemotion_api import Instance

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
    user = Instance(config_login.get('ELN_URL')).test_connection().login(config_login.get('ELN_USER'), config_login.get('ELN_PASS')).get_user()
    assert user.email == 'api_test@kit.edu'