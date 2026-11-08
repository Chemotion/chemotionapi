"""Device administration on a live ELN (M7.5). The stack configures no data collector."""
import random
import string

import pytest

from chemotion_api import Instance

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin(config_login):
    return Instance(config_login['ELN_URL']).login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS']).get_user()


def test_device_lifecycle(admin, logged_in_instance):
    abbr = 'D' + ''.join(random.choices(string.ascii_uppercase, k=3))
    device = admin.add_device(f'API probe {abbr}', abbr, serial_number='SN-1')
    try:
        assert [d['id'] for d in admin.list_devices(abbr)] == [device['id']]
        me = logged_in_instance.get_user()
        updated = admin.update_device(device['id'], people=[me.id], datacollector_method='filewatchersftp',
                                      datacollector_host='127.0.0.1', datacollector_user='nobody',
                                      datacollector_dir='/data', datacollector_authentication='password')
        assert updated['datacollector_host'] == '127.0.0.1'
        admin.remove_device_user(device['id'], me.id)
        with pytest.raises(LookupError):
            admin.remove_device_user(device['id'], me.id)
        assert admin.test_sftp(device['id'], '127.0.0.1', 'nobody')['status'] == 'error'
        assert isinstance(admin.local_collectors(), list)
        assert admin.device_metadata(device['id']) is None
        assert admin.save_device_metadata(device['id'], name='probe', description='NMR')['description'] == 'NMR'
    finally:
        with pytest.raises(ValueError, match='pass confirm'):
            admin.delete_device(device['id'], confirm='nope')
        admin.delete_device(device['id'], confirm=abbr)
    assert admin.list_devices(abbr) == []


def test_instruments(logged_in_instance):
    assert isinstance(logged_in_instance.instruments(), list)
    with pytest.raises(ValueError):
        logged_in_instance.instruments('vessels')
