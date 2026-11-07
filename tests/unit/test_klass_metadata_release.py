"""labimotion 2.3.4 (ELN main after v4.0.0) adds `metadata_release` to every klass entity.

The klass schemas forbid unknown properties, so a server that sends the field made a segment
fail validation of its own `to_dict()` (integration: test_segment_new_layer). The fixture is a
real `T TEST` segment klass payload from such a server, nested element klass included.
"""
import copy
import json
import os

import pytest
from jsonschema.exceptions import ValidationError

from chemotion_api.labImotion.items.validation import validate_generic_segment

FIXTURE = os.path.join(os.path.dirname(__file__), 'data', 'segment_klass_labimotion_2_3_4.json')


@pytest.fixture
def segment_klass():
    with open(FIXTURE) as f:
        return json.load(f)


def test_a_labimotion_2_3_4_segment_klass_validates(segment_klass):
    assert 'metadata_release' in segment_klass
    assert 'metadata_release' in segment_klass['element_klass']
    validate_generic_segment(segment_klass)


@pytest.mark.parametrize('value', [None, {}, {'some': 'release metadata'}])
def test_metadata_release_accepts_null_and_objects(segment_klass, value):
    segment_klass['metadata_release'] = value
    segment_klass['element_klass']['metadata_release'] = value
    validate_generic_segment(segment_klass)


def test_metadata_release_is_optional_as_on_older_servers(segment_klass):
    del segment_klass['metadata_release']
    del segment_klass['element_klass']['metadata_release']
    validate_generic_segment(segment_klass)


def test_metadata_release_must_be_an_object_or_null(segment_klass):
    bad = copy.deepcopy(segment_klass)
    bad['element_klass']['metadata_release'] = 'not an object'
    with pytest.raises(ValidationError):
        validate_generic_segment(bad)


def test_other_unknown_klass_fields_are_still_rejected(segment_klass):
    segment_klass['element_klass']['not_a_klass_field'] = 1
    with pytest.raises(ValidationError):
        validate_generic_segment(segment_klass)
