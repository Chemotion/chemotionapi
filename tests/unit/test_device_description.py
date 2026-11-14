"""Device descriptions: the only element whose ontology terms arrive pre-resolved.

An admin picks them from the TIB Terminology Service and the ELN stores the full IRI, so
unlike every other ontology store there is nothing to look up.
"""
from unittest.mock import MagicMock

import pytest

from chemotion_api.elements import DeviceDescription
from chemotion_api.elements.abstract_element import AbstractElement


def _device(json_data):
    """A DeviceDescription around raw server JSON, without a session or a load round trip."""
    d = DeviceDescription.__new__(DeviceDescription)
    from chemotion_api.utils import PropertyDict
    d.json_data = json_data
    d._data_loaded = True
    d._is_partial = False
    # Parse eagerly: the lazy `properties` path re-fetches from the server, which there is none
    # of here. _parse_properties() is still the thing under test.
    d._properties = PropertyDict(None, d._parse_properties())
    return d


def _terms(ontologies):
    d = _device({"ontologies": ontologies})
    return d.ontology_terms()


def test_terms_come_straight_from_the_stored_iri():
    terms = _terms([{"data": {"iri": "http://purl.obolibrary.org/obo/CHMO_0000575",
                              "label": "mass spectrometer"}}])
    assert terms == [{"iri": "http://purl.obolibrary.org/obo/CHMO_0000575",
                      "label": "mass spectrometer"}]


def test_deleted_annotations_are_dropped():
    """The ELN keeps removed terms in the column for undo; exporting one would annotate a
    device with a term its own users took off it."""
    assert _terms([{"data": {"iri": "http://e/A", "label": "kept"}},
                   {"data": {"iri": "http://e/B", "label": "removed"}, "is_deleted": True}]) \
        == [{"iri": "http://e/A", "label": "kept"}]


def test_a_term_without_a_label_falls_back_to_an_identifier():
    assert _terms([{"data": {"iri": "http://e/C", "obo_id": "CHMO:1"}}])[0]["label"] == "CHMO:1"


def test_duplicate_iris_are_emitted_once():
    assert len(_terms([{"data": {"iri": "http://e/D", "label": "x"}},
                       {"data": {"iri": "http://e/D", "label": "x again"}}])) == 1


@pytest.mark.parametrize("ontologies", [None, [], ["junk"], [{}], [{"data": None}],
                                        [{"data": {"iri": ""}}], [{"data": {"label": "no iri"}}]])
def test_malformed_annotations_are_ignored(ontologies):
    assert _terms(ontologies) == []


def test_the_element_lists_and_saves_against_its_own_endpoint():
    """Regression: every unmodelled type fell through to /api/v1/generic_elements, so a
    device description listed as a generic and came back empty."""
    assert AbstractElement.get_url("device_description") == "/api/v1/device_descriptions"
    assert AbstractElement.get_response_key("device_description") == "device_description"


def test_an_unmodelled_builtin_type_refuses_by_name():
    """The error should name the type and the scope, not read 'Generic type X cannot be found'."""
    from chemotion_api.elements import ElementSet
    es = ElementSet.__new__(ElementSet)
    es._element_type = {"name": "no_such_type", "is_generic": False}
    with pytest.raises(TypeError) as exc:
        es._get_element_class()
    message = str(exc.value)
    assert "no_such_type" in message
    assert "does not model" in message
    assert "device_description" in message, "the message should name what IS supported"


# --- creating one (2026-11-13) ---------------------------------------------------------------

def test_a_refused_create_raises_instead_of_passing_as_created():
    """The create route answers a RecordInvalid with 201 and ``{"errors": ...}``."""
    d = _device({})
    d._element_type = "device_description"
    with pytest.raises(ValueError, match="refused"):
        d._record_from_create({"errors": {"name": ["is invalid"]}})
    assert d._record_from_create({"device_description": {"id": 7}}) == {"id": 7}


def test_the_empty_template_parses_and_covers_every_modelled_field():
    import json
    import os
    from chemotion_api.elements.device_description import DEVICE_FIELDS
    import chemotion_api
    path = os.path.join(os.path.dirname(chemotion_api.__file__), 'elements', 'empty_elements',
                        'device_description.json')
    with open(path) as f:
        template = json.load(f)
    assert template["type"] == "device_description"
    assert set(DEVICE_FIELDS) <= set(template), "a modelled field the template does not seed"
    props = _device(template).properties
    assert props["name"] == "New device description"
    assert props["general_tags"] == [], "the server declares general_tags as an Array"
