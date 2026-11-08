"""Sequence-based macromolecule samples (M4.4), offline, against a real ELN `main` payload."""
import json
import os

import pytest
import requests

from chemotion_api.connection import request_error
from chemotion_api.elements.sbmm import SbmmSample, SbmmUpdateNotAllowed, macromolecule_attributes
from chemotion_api.schema_manager import SchemaManager

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'sbmm_sample_v4_main.json')


class _About:
    status_code, text = 200, '<h4>Version: v4.0.0</h4>'


class _Session:
    schema_manager = SchemaManager(_About())
    _host_url = 'http://eln.test'


class _Segments:
    all_classes = []


def _payload():
    with open(FIXTURE) as f:
        return json.load(f)


def _sample(payload=None):
    s = SbmmSample(_Segments(), _Session(), json_data=payload or _payload())
    s._data_loaded = True
    return s


def test_properties_and_attributes():
    s = _sample()
    assert s.properties['name'] == 'LYZ batch' and s.macromolecule['short_name'] == 'LYZ2'
    out = s._clean_properties_data()
    attrs = out['sequence_based_macromolecule_attributes']
    assert (attrs['uniprot_derivation'], attrs['short_name'], attrs['sequence']) == (
        'uniprot_unknown', 'LYZ2', 'KVFGRCELAAAMKRHGLDNYRG')
    assert 'id' not in attrs['protein_sequence_modification_attributes']
    assert 'splitted_sequence' not in attrs and 'sequence_based_macromolecule' not in out


def test_uniprot_entries_send_no_modifications():
    attrs = macromolecule_attributes({'uniprot_derivation': 'uniprot', 'primary_accession': 'P61626',
                                      'sbmm_type': 'protein', 'protein_sequence_modifications': {'x': 1}})
    assert attrs == {'uniprot_derivation': 'uniprot', 'primary_accession': 'P61626', 'sbmm_type': 'protein'}


def test_modified_entries_name_their_parent():
    attrs = macromolecule_attributes({'uniprot_derivation': 'uniprot_modified', 'short_name': 'x', 'sequence': 'K',
                                      'parent': {'id': 7}})
    assert attrs['parent_identifier'] == '7'


@pytest.mark.parametrize('sbmm, match', [
    ({'uniprot_derivation': None}, 'uniprot_derivation'),
    ({'uniprot_derivation': 'uniprot', 'primary_accession': None}, 'primary_accession'),
    ({'uniprot_derivation': 'uniprot_unknown', 'short_name': '', 'sequence': 'K'}, 'short_name'),
])
def test_incomplete_macromolecules_are_refused(sbmm, match):
    s = _sample()
    s.macromolecule.update(sbmm)
    with pytest.raises(ValueError, match=match):
        s.clean_data()


def test_a_shared_macromolecule_conflict_becomes_its_own_error(monkeypatch):
    res = requests.Response()
    res.status_code = 403
    res._content = json.dumps({'error': {'type': 'SbmmUpdateNotAllowed', 'message': 'used elsewhere',
                                         'original_sbmm': {'id': 2}, 'requested_changes': {'id': 2}}}).encode()

    def failing_save(self, load_after_save=False):
        raise request_error(res, 'saving')
    monkeypatch.setattr('chemotion_api.elements.abstract_element.AbstractElement.save', failing_save)
    with pytest.raises(SbmmUpdateNotAllowed, match='used elsewhere') as err:
        _sample().save()
    assert err.value.original == {'id': 2}
