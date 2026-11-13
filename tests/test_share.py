import pytest
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


def test_share_detail_level_withholds_fields(instance_with_collection, config_login):
    """A share below detail level 10 must not hand the recipient the sample's details.

    `detail_level` is a required argument precisely because it decides disclosure, so an
    unenforced level would be a leak that looks like a working feature. Shares two collections
    with MM — one at 0, one at 10 — and compares what MM receives for the same kind of sample.
    """
    import uuid
    owner = instance_with_collection['instance']
    root = owner.get_root_collection()
    labels = {}
    for level in (0, 10):
        label = f'API_TEST_detail_{level}_{uuid.uuid4().hex[:6]}'
        root.add_collection(label)
        root.save()
        col = owner.get_root_collection(reload=True).get_collection(label)
        sample = col.new_sample_smiles('CCO')
        sample.properties['description'] = 'confidential note'
        sample.properties['target_amount']['value'] = 1.25
        sample.save()
        mm = next(u for u in owner.find_user_by_name('Max Mustermann') if u.name_abbreviation == 'MM')
        col.share(CollectionSharePermission.ReadElements, mm, detail_level=level)
        labels[level] = (label, sample.id)

    recipient = Instance(config_login['ELN_URL']).test_connection().login('MM', 'thebestpasswordever')
    payload = {}
    for level, (_, sample_id) in labels.items():
        res = recipient._con.get(f'/api/v1/samples/{sample_id}')
        assert res.status_code == 200, res.text
        payload[level] = res.json()['sample']

    full, restricted = payload[10], payload[0]
    assert full['description'] and 'confidential note' in str(full['description'])
    assert full['target_amount_value'] == 1.25
    assert restricted['is_restricted'] is True
    assert 'confidential note' not in str(restricted.get('description'))
    assert restricted['target_amount_value'] == '***'      # the server's mask for a withheld value

    # And the client copes with it: the recipient can list and read the restricted sample, sees
    # the withheld fields as WITHHELD rather than as empty, and cannot save it back.
    from chemotion_api.utils.withheld import WITHHELD
    shared = {c.label: c for c in recipient.get_root_collection().sync_root.children}
    sample = next(iter(shared[labels[0][0]].get_samples()))
    assert sample.is_restricted
    assert sample.properties['description'] is WITHHELD
    assert sample.properties['target_amount']['value'] is WITHHELD
    with pytest.raises(PermissionError):
        sample.save()
    visible = next(iter(shared[labels[10][0]].get_samples()))
    assert not visible.is_restricted
    assert visible.properties['target_amount']['value'] == 1.25
