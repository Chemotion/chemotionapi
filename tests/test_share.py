from chemotion_api import Instance
from chemotion_api.collection import Collection, SyncPermission


def test_new_user(config_login):
    instance = Instance(config_login['ELN_URL']).test_connection().login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS'])
    user = instance.get_user().create_person(first_name='TestUSer', last_name="Mega", email='aa@bb.cc', name_abbreviation='VDR', password='QWEasd123!"§')
    assert user.name_abbreviation == 'VDR'

def test_share_group(instance_with_collection, config_login):
    instance = instance_with_collection['instance']
    user = instance.find_user_by_name('TestUSer')

    col: Collection = instance_with_collection['main_collection']
    col.share(SyncPermission.Read, *user)
    instance = Instance(config_login['ELN_URL']).test_connection().login('VDR', 'QWEasd123!"§')
    c = instance.get_root_collection().sync_root.children[0]
    assert c.label == 'with VDR'
    assert c.children[0].label == col.label
