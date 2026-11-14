"""SBMM samples against a live ELN v4.0.1 (needs the server to reach UniProt)."""
from chemotion_api.collection import Collection
from chemotion_api.elements import SbmmSample
from chemotion_api.elements.empty_elements import init_container


def test_sbmm_sample_from_uniprot_round_trip(instance_with_collection: dict):
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    sample = col.new_sbmm_sample(uniprot='P69905')
    sample.properties['name'] = 'Hb alpha, lot 1'
    sample.properties['purity'] = 0.9
    sample.save()
    protein = instance.get_sbmm_sample(sample.id).macromolecule
    assert protein['primary_accession'] == 'P69905'
    assert protein['short_name'] == 'Hemoglobin subunit alpha'

    listed = next(s for s in col.get_sbmm_samples() if s.id == sample.id)
    assert isinstance(listed, SbmmSample)
    listed.properties['supplier'] = 'Acme'
    listed.properties['concentration'] = {'value': 2.5, 'unit': 'mg/L'}
    listed.save()

    again = instance.get_sbmm_sample(sample.id)
    assert again.properties['supplier'] == 'Acme'
    assert again.properties['purity'] == 0.9
    assert again.properties['concentration'] == {'value': 2.5, 'unit': 'mg/L'}
    assert again.macromolecule['id'] == protein['id']                  # protein untouched
    assert again.macromolecule['sequence'] == protein['sequence']


def test_a_sample_of_a_hand_described_protein_saves(instance_with_collection: dict):
    """Created the way the web UI does (no UniProt entry); the client must save it unchanged."""
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    res = instance._con.post('/api/v1/sequence_based_macromolecule_samples', data={
        'collection_id': col.id, 'name': 'custom', 'container': init_container(),
        'sequence_based_macromolecule_attributes': {
            'sbmm_type': 'protein', 'uniprot_derivation': 'uniprot_unknown',
            'short_name': 'API test peptide', 'sequence': 'MKTAYIAKQR',
            'protein_sequence_modification_attributes': {},
            'post_translational_modification_attributes': {}}})
    assert res.status_code == 201, res.text
    sample = instance.get_sbmm_sample(res.json()['sequence_based_macromolecule_sample']['id'])
    before = sample.macromolecule
    sample.properties['supplier'] = 'in house'
    sample.save()
    again = instance.get_sbmm_sample(sample.id)
    assert again.properties['supplier'] == 'in house'
    assert again.macromolecule['id'] == before['id']
    assert again.macromolecule['sequence'] == 'MKTAYIAKQR'
