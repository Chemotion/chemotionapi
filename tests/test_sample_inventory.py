"""Sample inventory record and molecule names against a live ELN v4 — the two calls the
chemotion-sample-manager had to hand-roll."""
import uuid

from chemotion_api.collection import Collection


def test_chemical_record_create_then_update(instance_with_collection: dict):
    col: Collection = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.save()

    chem = sample.get_chemical()
    assert not chem.exists

    chem.cas = '64-17-5'
    chem.data['vendor'] = 'Acme'
    chem.save()
    assert chem.exists

    again = sample.get_chemical()
    assert again.exists and again.cas == '64-17-5' and again.data['vendor'] == 'Acme'

    again.data['vendor'] = 'Bcme'
    again.save()
    assert sample.get_chemical().data['vendor'] == 'Bcme'


def test_molecule_names_add_and_select(instance_with_collection: dict):
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.save()
    molecules = instance.molecule()
    molecule_id = sample.molecule['id']

    before = molecules.get_names(molecule_id)
    assert before, 'a molecule from SMILES has at least its generated names'

    label = f'API test name {uuid.uuid4().hex[:6]}'
    added = molecules.add_name(molecule_id, label)
    assert added.name == label
    assert added in molecules.get_names(molecule_id)

    sample.molecule_name_id = added.id
    sample.save()
    assert instance.get_sample(sample.id).molecule_name_id == added.id


def test_names_of_an_unknown_molecule_are_empty(logged_in_instance):
    assert logged_in_instance.molecule().get_names(2_000_000_000) == []
