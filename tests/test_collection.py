import uuid

import pytest

from chemotion_api import Instance

def test_new_collection(logged_in_instance: Instance, delete_col_prefix: str):
    col = logged_in_instance.get_root_collection()
    col.add_collection(delete_col_prefix + 'Test_collection')
    col.save()


    tc = col.get_collection(delete_col_prefix + 'Test_collection')
    assert tc.get_path() == f'/{delete_col_prefix}Test_collection'
    tc.delete()
    col.save()
    col = logged_in_instance.get_root_collection()
    with pytest.raises(ModuleNotFoundError) as e:
        col.get_collection(delete_col_prefix + 'Test_collection')

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



def test_move_collection(prepare_manipulation):
    name = prepare_manipulation['name']
    root_col = prepare_manipulation['root_col']
    b = prepare_manipulation['b_col']
    b.move(f'/{name}/A')
    root_col.save()
    with pytest.raises(ModuleNotFoundError) as e:
        root_col.get_collection(name + '/B')

    assert root_col.get_collection(name + '/A/B').label == 'B'
    assert root_col.get_collection(name).get_collection(['A', 'B']).label == 'B'
    assert root_col.get_collection(name).get_collection('A/B').label == 'B'
    assert root_col.get_collection(name).get_collection(f'/{name}/A/B').label == 'B'


def test_rename_collection(prepare_manipulation):
    name = prepare_manipulation['name']
    root_col = prepare_manipulation['root_col']
    b = prepare_manipulation['b_col']
    b.label = 'B_NEW'
    root_col.save()

    assert root_col.get_collection(name + '/B_NEW').label == 'B_NEW'

def test_get_create_collection(logged_in_instance, delete_col_prefix):
    root_col = logged_in_instance.get_root_collection()
    a = root_col.get_or_create_collection(delete_col_prefix + 'A')
    b = a.get_or_create_collection('B')
    b1 = a.get_or_create_collection('B')


    assert b1.id == b.id


def test_sync(prepare_manipulation):
    root_col = prepare_manipulation['root_col']
    sync_root = root_col.sync_root
    with pytest.raises(Exception)   as e:
        sync_root.add_collection('A')




def test_move_assign_remove_elements(instance_with_collection):
    root = instance_with_collection['instance'].get_root_collection()
    main = root.get_collection(instance_with_collection['name'])
    a = main.get_or_create_collection('A')
    b = main.get_or_create_collection('B')
    sample = a.new_sample_smiles('CCO')
    sample.save()
    reaction = a.new_reaction()
    reaction.save()

    def ids(col):
        return {e.id for e in col.get_samples()} | {e.id for e in col.get_reactions()}

    a.move_elements(b, sample, reaction)
    assert ids(a) == set() and ids(b) == {sample.id, reaction.id}
    sample.assign_to(a)
    assert ids(a) == {sample.id} and ids(b) == {sample.id, reaction.id}
    b.remove_elements(sample)
    assert ids(b) == {reaction.id}
    # v4 answers 403 for this, not a generic failure: the 'All' collection is every element's
    # home, so removing from it would mean deleting. The v3 line raised ConnectionError here.
    with pytest.raises(PermissionError, match='ALL-Collection'):
        root.remove_elements(sample)
