"""SBMM samples offline, on a payload captured from ELN v4.0.1 (protein P69905 from UniProt)."""
import json
import os
from types import SimpleNamespace

import pytest

from chemotion_api.elements import SbmmSample
from chemotion_api.elements.abstract_element import AbstractElement

SESSION = SimpleNamespace(_host_url='http://localhost',
                          schema_manager=SimpleNamespace(generate_model_type=lambda *a: 'chemotion:type'))
SEGMENTS = SimpleNamespace(all_classes=[])
FIXTURE = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'sbmm', 'sbmm_create.json')


def _sample(**overrides):
    with open(FIXTURE) as f:
        data = json.load(f)['sequence_based_macromolecule_sample'] | overrides
    s = SbmmSample(SEGMENTS, SESSION, json_data=data)
    s._data_loaded = True
    return s


def test_routing():
    assert AbstractElement.get_url('sequence_based_macromolecule_sample') == '/api/v1/sequence_based_macromolecule_samples'
    assert AbstractElement.get_response_key('sequence_based_macromolecule_sample') == 'sequence_based_macromolecule_sample'


def test_quantities_are_value_unit_pairs_and_round_trip():
    s = _sample(purity=0.5, molarity_value=2.0, molarity_unit='mmol/L')
    assert s.properties['molarity'] == {'value': 2.0, 'unit': 'mmol/L'}
    s.properties['molarity']['value'] = '3.5'        # coerced per field
    out = s._clean_properties_data()
    assert (out['molarity_value'], out['molarity_unit'], out['purity']) == (3.5, 'mmol/L', 0.5)


def test_the_protein_is_sent_back_by_accession_only():
    out = _sample()._clean_properties_data()
    assert out['sequence_based_macromolecule_attributes'] == {
        'sbmm_type': 'protein', 'uniprot_derivation': 'uniprot', 'primary_accession': 'P69905'}


def test_macromolecule_is_a_read_only_copy():
    s = _sample()
    m = s.macromolecule
    assert m['short_name'] == 'Hemoglobin subunit alpha'
    m['short_name'] = 'changed'
    assert s.macromolecule['short_name'] == 'Hemoglobin subunit alpha'


def test_a_hand_described_protein_is_sent_back_as_loaded():
    with open(FIXTURE) as f:
        protein = json.load(f)['sequence_based_macromolecule_sample']['sequence_based_macromolecule']
    protein = protein | {'uniprot_derivation': 'uniprot_unknown', 'primary_accession': None,
                         'protein_sequence_modifications': {'id': 4, 'modification_n_terminal': True},
                         'post_translational_modifications': {'id': 5, 'phosphorylation_enabled': False}}
    identity = _sample(sequence_based_macromolecule=protein)._clean_properties_data()[
        'sequence_based_macromolecule_attributes']
    assert identity['uniprot_derivation'] == 'uniprot_unknown'
    assert identity['short_name'] == protein['short_name'] and identity['sequence'] == protein['sequence']
    assert identity['protein_sequence_modification_attributes'] == {'modification_n_terminal': True}
    assert identity['post_translational_modification_attributes'] == {'phosphorylation_enabled': False}
    assert 'primary_accession' not in identity


@pytest.mark.parametrize("field, bad", [('formulation', 'gas'), ('purity', 'high'),
                                         ('obtained_by', 'stolen')])
def test_writes_are_validated(field, bad):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _sample().properties[field] = bad
