"""Fields ELN v4.0.0 added to the entities, and the one it replaced.

Comparing the exposed fields of every entity between the `v4.0.0-rc` tag our test stack pins and
the released `v4.0.0` gives five additions and no removals (see AI/check_api_drift.py). Purely
additive, so nothing broke — but a field the client never reads is a field the client cannot use,
and one of them replaces a boolean we were still writing.
"""
import pytest

from chemotion_api.models import ReactionPropertiesModel


class _Elem:
    """The `can_update` accessor in isolation, without a Connection behind it."""

    def __init__(self, json_data):
        from chemotion_api.elements.abstract_element import AbstractElement
        self.json_data = json_data
        self.can_update = AbstractElement.can_update.fget(self)


@pytest.mark.parametrize("payload, expected", [
    ({"can_update": True}, True),
    ({"can_update": False}, False),
    ({}, None),                      # an entity type that does not expose it
    ({"can_update": None}, None),    # or a listing payload that omitted it
    ({"can_update": "yes"}, None),   # never coerce a string into a permission
])
def test_can_update_reports_only_what_the_server_said(payload, expected):
    """`None` means "the server did not say" — which is not the same as "no". A caller that
    treats a missing hint as a refusal would refuse writes that would have succeeded."""
    assert _Elem(payload).can_update is expected


@pytest.mark.parametrize("payload, expected", [
    ({"previewable": True}, True),
    ({"previewable": False}, False),
    ({}, None),
])
def test_previewable_reports_only_what_the_server_said(payload, expected):
    from chemotion_api.elements.attachments import Attachment
    att = Attachment.__new__(Attachment)
    dict.__init__(att, payload)
    assert att.previewable is expected


@pytest.mark.parametrize("mode", ["solvents_only", "combined", "reaction_volume"])
def test_every_concentration_mode_the_server_allows_round_trips(mode):
    """v4 replaced `use_reaction_volume` with a three-valued mode. The boolean maps to only two of
    them, so `combined` was unreachable from this client until the mode itself was carried."""
    assert ReactionPropertiesModel.model_validate({"concentration_mode": mode}).concentration_mode == mode


def test_an_unknown_concentration_mode_is_rejected():
    """The server validates against Reaction::CONCENTRATION_MODES; failing here beats a 400."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ReactionPropertiesModel.model_validate({"concentration_mode": "whatever"})


def test_concentration_mode_defaults_to_absent_not_guessed():
    """Omitted means "not stated". Inventing `solvents_only` would silently change a reaction on
    the next save."""
    assert ReactionPropertiesModel.model_validate({}).concentration_mode is None


def test_can_update_does_not_raise_on_an_element_with_no_payload():
    """`json_data` is nullable by design — a freshly constructed element has none. A property
    whose contract is "None means the server did not say" must not crash instead of saying it.
    Found by adversarial review of this file's own first version, which did `cast(dict, …).get`.
    """
    from chemotion_api.elements.abstract_element import AbstractElement

    class _Bare:
        json_data = None

    assert AbstractElement.can_update.fget(_Bare()) is None
