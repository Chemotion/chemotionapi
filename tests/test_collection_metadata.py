"""Collection and research plan metadata, and taking ownership, on a live ELN (M3.6)."""
import random
import string

import pytest

from chemotion_api import Instance
from chemotion_api.collection import CollectionSharePermission

pytestmark = pytest.mark.integration


def test_collection_metadata(instance_with_collection):
    col = instance_with_collection['main_collection']
    assert col.metadata() is None
    data = {'title': 'Dataset', 'creators': [{'givenName': 'Ada', 'familyName': 'Lovelace'}]}
    assert col.save_metadata(data) == data
    assert col.metadata() == data


def test_research_plan_metadata(instance_with_collection):
    plan = instance_with_collection['main_collection'].new_research_plan()
    plan.save()
    assert plan.metadata() is None
    saved = plan.save_metadata(title='Plan', subject='chemistry')
    assert (saved['title'], saved['subject']) == ('Plan', 'chemistry')
    plan.save_metadata(version='2')
    assert (plan.metadata()['title'], plan.metadata()['version']) == ('Plan', '2')
    with pytest.raises(ValueError, match='Unknown metadata'):
        plan.save_metadata(colour='red')


@pytest.fixture()
def second_person(config_login):
    admin = Instance(config_login['ELN_URL']).login(config_login['ELN_ADMIN_USER'], config_login['ELN_ADMIN_PASS'])
    abbr = ''.join(random.choices(string.ascii_uppercase, k=4))
    password = 'QWEasd123!"§'
    person = admin.get_user().create_person(first_name='Heir', last_name=f'Apparent{abbr}', name_abbreviation=abbr,
                                            password=password, email=f'{abbr.lower()}@heir.example')
    return person, Instance(config_login['ELN_URL']).login(abbr, password)


def test_take_ownership(instance_with_collection, second_person):
    col = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.save()
    person, heir = second_person
    shared = heir.get_root_collection().sync_root.children
    assert shared == []

    col.share(CollectionSharePermission.PassOwnership, person, detail_level=10)
    (offered,) = heir.get_root_collection().sync_root.children
    assert offered.take_ownership()['label'] == col.label
    mine = heir.get_root_collection().get_collection(col.label)
    assert [s.id for s in mine.get_samples(per_page=None)] == [sample.id]


def test_taking_ownership_without_an_offer_is_refused(instance_with_collection, second_person):
    col = instance_with_collection['main_collection']
    person, heir = second_person
    col.share(CollectionSharePermission.ReadElements, person, detail_level=10)
    (shared,) = heir.get_root_collection().sync_root.children
    with pytest.raises(PermissionError):
        shared.take_ownership()
