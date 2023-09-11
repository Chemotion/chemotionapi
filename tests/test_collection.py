import uuid

import pytest

from chemotion_api import Instance

def test_new_collection(logged_in_instance: Instance):
    col = logged_in_instance.get_root_collection()
    col.add_collection('Test_collection')
    col.save()


    tc = col.get_collection('Test_collection')
    assert tc.get_path() == '/Test_collection'
    tc.delete()
    col.save()
    col = logged_in_instance.get_root_collection()
    with pytest.raises(ModuleNotFoundError) as e:
        col.get_collection('Test_collection')

@pytest.fixture()
def prepare_manipulation(logged_in_instance):
    name = uuid.uuid4().__str__()
    root_col = logged_in_instance.get_root_collection()
    new_root = root_col.add_collection(name)
    new_root.add_collection('A')
    new_root.add_collection('B')
    root_col.save()
    yield {
        'instance': logged_in_instance,
        'name': name,
        'root_col': root_col,
        'a_col': new_root.get_collection('A'),
        'b_col': new_root.get_collection('B')
    }
    new_root.delete()
    root_col.save()


def test_move_collection(prepare_manipulation):
    name = prepare_manipulation['name']
    root_col = prepare_manipulation['root_col']
    b = prepare_manipulation['b_col']
    b.move('/{}/A'.format(name))
    root_col.save()
    with pytest.raises(ModuleNotFoundError) as e:
        root_col.get_collection(name + '/B')

    assert root_col.get_collection(name + '/A/B').label == 'B'
    assert root_col.get_collection(name).get_collection(['A', 'B']).label == 'B'
    assert root_col.get_collection(name).get_collection('A/B').label == 'B'
    assert root_col.get_collection(name).get_collection('/{}/A/B'.format(name)).label == 'B'


def test_rename_collection(prepare_manipulation):
    name = prepare_manipulation['name']
    root_col = prepare_manipulation['root_col']
    b = prepare_manipulation['b_col']
    b.label = 'B_NEW'
    root_col.save()

    assert root_col.get_collection(name + '/B_NEW').label == 'B_NEW'

def test_get_create_collection(logged_in_instance):
    root_col = logged_in_instance.get_root_collection()
    a = root_col.get_or_create_collection('A')
    b = a.get_or_create_collection('B')
    b1 = a.get_or_create_collection('B')


    assert b1.id == b.id


def test_sync(prepare_manipulation):
    root_col = prepare_manipulation['root_col']
    sync_root = root_col.sync_root
    with pytest.raises(Exception)   as e:
        sync_root.add_collection('A')


