"""The klass schemas accept exactly the fields the server sends — no more, no less.

These schemas set ``additionalProperties: False``, which is deliberate: it turns a field the
server started sending into a loud failure rather than silence. The cost is that **every new
server field is a breaking change until it is declared here**, so the declarations need a test
that does not require a live server.

They did not have one. When LabIMotion 2.3.4 (ELN v4.0.1) added ``metadata_release`` to
``generic_klass_entity.rb``, every klass payload was rejected and the whole generic API became
unusable — and the only thing that noticed was a 13-minute integration suite against a 4.0.1
stack. The 400 offline tests stayed green throughout. These tests close that gap.
"""
import pytest
from jsonschema import Draft202012Validator, ValidationError

from chemotion_api.labImotion.items.validation.schemas.abstract_element_schema import (
    generic_element_schema,
)

#: A klass payload shaped like the ones ELN v4.0.1 actually returns. Every required key is
#: present so that a failure points at the field under test rather than at a missing one.
MINIMAL_KLASS = {
    "id": 1,
    "uuid": "5ad5e303-5d9b-44f2-80b9-ed6962465d36",
    "label": "T TEST",
    "desc": "a klass",
    "properties_template": {},
    "properties_release": {},
    "is_active": True,
    "version": "0.1",
    "place": 1,
    "released_at": "2026-11-11T05:31:36+0000",
    "identifier": "245ee4ce-38ce-42ef-aa7f-e484674b96b2",
    "sync_time": None,
    "created_at": "2026-11-11T05:31:36+0000",
    "updated_at": "2026-11-11T05:31:37+0000",
}


def _validate(payload):
    """Validate against the klass schema alone, with ``$ref``s to sibling schemas stubbed out.

    ``properties_template`` / ``properties_release`` ``$ref`` the properties schema through a
    registry the full client assembles at import time. These tests are about the *klass* field
    list, so the refs are replaced with permissive stubs rather than pulling that in.
    """
    schema = {**generic_element_schema}
    schema["properties"] = {
        key: ({} if isinstance(value, dict) and "$ref" in value else value)
        for key, value in schema["properties"].items()
    }
    Draft202012Validator(schema).validate(payload)


def test_minimal_klass_payload_is_valid():
    """Guards the fixture itself: if this fails, the tests below are testing nothing."""
    _validate(MINIMAL_KLASS)


@pytest.mark.parametrize("value", [{}, None, {"pkg": {"eln": {"version": "v4.0.1"}}}])
def test_metadata_release_is_accepted(value):
    """Added by LabIMotion 2.3.4; the server sends ``{}``, a populated object, or omits it."""
    _validate({**MINIMAL_KLASS, "metadata_release": value})


def test_metadata_release_is_optional():
    """It is only present where the endpoint preloaded the revision map, so it is not required."""
    assert "metadata_release" not in generic_element_schema["required"]
    _validate(MINIMAL_KLASS)


def test_an_undeclared_field_is_still_rejected():
    """The point of ``additionalProperties: False``.

    If this ever passes, the schema has been loosened and the next server-side addition will be
    absorbed silently instead of failing here — which is the failure mode these tests exist to
    prevent. Loosening is not the way to fix a rejected payload; declaring the field is.
    """
    assert generic_element_schema["additionalProperties"] is False
    with pytest.raises(ValidationError):
        _validate({**MINIMAL_KLASS, "a_field_no_server_sends": 1})
