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
    assert user.initials == 'API'
    assert user.name_abbreviation == 'API'
    assert user.email == 'api@kit.edu'
    with pytest.raises(Exception):
        user.fetchDevices()


# `test_get_admin_devices` and `test_create_devices` were deleted in 401.0 along with the
# `DeviceManager` methods they covered. Neither ran: one was a bare `pass` over a commented-out
# body, the other a `# TODO` followed by `return`. Both read as coverage — in the file and in a
# collected-test count — while asserting nothing, which is how those dead endpoints survived.
# `test_get_user` also asserted that `create_new_device` *raises*; that passed only because the
# route 404s, so it has gone too rather than being carried forward as a tautology.
#
# The test below replaces them, against the method that actually works.


def test_create_device_and_delete(config_login):
    """`Admin.create_device()` is the supported way to create a device user.

    This is what the deleted tests should have covered. It exercises the real route
    (`/api/v1/admin_devices`), checks a usable typed `Device` comes back rather than a raw
    payload, and asserts the duplicate case raises — the server answers a rejected
    `name_abbreviation` with `201` and an `errors` body, so a wrapper that trusted the status
    code would report a creation that did not happen.
    """
    instance = Instance(config_login.get('ELN_URL')).test_connection().login(
        config_login.get('ELN_ADMIN_USER'), config_login.get('ELN_ADMIN_PASS'))
    admin = instance.get_user()
    name_abbreviation = random_char(3).upper()

    device = admin.create_device('Probe Device', name_abbreviation)
    try:
        assert device.id is not None
        assert device.name_abbreviation == name_abbreviation
        # The returned object must be usable, not just populated: `DeviceEntity` carries no
        # `type`, so without one `is_device()` raises AttributeError on a plain accessor.
        assert device.is_device()
        with pytest.raises(ConnectionError):
            admin.create_device('Probe Device', name_abbreviation)
    finally:
        device.delete()
