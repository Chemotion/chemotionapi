from chemotion_api import Instance
from chemotion_api.collection import Collection, CollectionSharePermission


def test_new_user(config_login):
    instance = Instance(config_login['ELN_URL']).test_connection().login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS'])
    user = instance.get_user().create_person(first_name='TestUSer', last_name="Mega", email='aa@bb.cc', name_abbreviation='VDR', password='QWEasd123!"§')
    assert user.name_abbreviation == 'VDR'

def test_share_group(instance_with_collection, config_login):
    instance = instance_with_collection['instance']
    user = instance.find_user_by_name('TestUSer')

    col: Collection = instance_with_collection['main_collection']
    col.share(CollectionSharePermission.ReadElements, *user, detail_level=10)
    instance = Instance(config_login['ELN_URL']).test_connection().login('VDR', 'QWEasd123!"§')
    shared = instance.get_root_collection().sync_root.children
    # ELN v4 returns shared collections directly in `shared_with_me`, each carrying its owner.
    # Pre-v4 they arrived nested under a synthetic "with <recipient>" parent, which no longer
    # exists — so the shared collection is now a direct child rather than a grandchild.
    assert [c.label for c in shared] == [col.label]
