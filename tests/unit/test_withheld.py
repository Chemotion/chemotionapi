"""Elements shared below the full detail level: withheld fields, loading, and refusing to save.

The fixtures are real ELN v4.0.1 payloads (2026-11-13): a collection shared with a second user at
detail level 0, then fetched as that user. The server sets `is_restricted: true` and puts '***'
where it withheld a value. The client used to crash loading such a sample (pydantic rejected '***'
for purity, density, molarity), so the recipient could not even list it.
"""
import json
import os
import pickle
from types import SimpleNamespace

import pytest

from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.elements.sample import Sample
from chemotion_api.elements.wellplate import Wellplate
from chemotion_api.utils.withheld import WITHHELD, Withheld, WithheldValueError, mark_withheld

SESSION = SimpleNamespace(_host_url='http://localhost',
                          schema_manager=SimpleNamespace(generate_model_type=lambda *args: 'chemotion:type'))
SEGMENTS = SimpleNamespace(all_classes=[])
FIXTURES = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'restricted')
KINDS = [('sample', Sample), ('reaction', Reaction), ('wellplate', Wellplate), ('research_plan', ResearchPlan)]


def _payload(kind, where='detail'):
    with open(os.path.join(FIXTURES, f'restricted_{kind}.json')) as f:
        data = json.load(f)
    return data['detail'][kind] if where == 'detail' else data['listing'][kind + 's'][0]


def _element(cls, payload):
    element = cls(SEGMENTS, SESSION, json_data=payload)
    element._data_loaded = True          # no server: do not try to fetch the full record
    return element


@pytest.mark.parametrize("kind, cls", KINDS)
@pytest.mark.parametrize("where", ['detail', 'listing'])
def test_a_restricted_element_loads(kind, cls, where):
    element = _element(cls, _payload(kind, where))
    assert element.is_restricted
    element.properties                   # parsing must not raise


def test_withheld_sample_fields_read_as_the_sentinel_not_as_empty():
    s = _element(Sample, _payload('sample'))
    p = s.properties
    for key in ('description', 'location', 'purity', 'density', 'name', 'short_label',
                'melting_point_lowerbound', 'boiling_point_upperbound'):
        assert p[key] is WITHHELD, key
    assert p['target_amount']['value'] is WITHHELD
    assert p['molarity']['unit'] is WITHHELD          # not the string 'WITHHELD'
    assert s.short_label is WITHHELD


def test_withheld_reaction_timestamps_are_not_read_as_missing():
    r = _element(Reaction, _payload('reaction'))
    assert r.properties['timestamp_start'] is WITHHELD
    assert r.properties['timestamp_stop'] is WITHHELD


def test_an_unrestricted_payload_keeps_a_literal_three_stars():
    """'***' can be a value somebody typed; only a restricted payload is the server's mask."""
    payload = _payload('wellplate') | {'is_restricted': False, 'description': '***'}
    w = _element(Wellplate, payload)
    assert not w.is_restricted
    assert w.json_data['description'] == '***'


@pytest.mark.parametrize("kind, cls", KINDS)
def test_saving_a_restricted_element_is_refused_before_any_request(kind, cls):
    element = _element(cls, _payload(kind))
    element._session = SimpleNamespace(post=_no_request, put=_no_request, get=_no_request)
    with pytest.raises(PermissionError, match="below the full detail level"):
        element.save()


def _no_request(*args, **kwargs):
    raise AssertionError("save() must not reach the server for a restricted element")


def test_using_a_withheld_value_as_a_number_says_why():
    with pytest.raises(WithheldValueError, match="withheld"):
        float(WITHHELD)
    with pytest.raises(PermissionError):
        WITHHELD * 2
    assert WITHHELD is not None and WITHHELD != 0


def test_the_sentinel_is_a_singleton_and_survives_pickling():
    assert Withheld() is WITHHELD
    assert pickle.loads(pickle.dumps(WITHHELD)) is WITHHELD
    assert repr(WITHHELD) == 'WITHHELD'


def test_mark_withheld_reaches_nested_values():
    data = {'a': '***', 'b': {'c': '***', 'd': 'x'}, 'e': ['***', 1]}
    mark_withheld(data)
    assert data == {'a': WITHHELD, 'b': {'c': WITHHELD, 'd': 'x'}, 'e': [WITHHELD, 1]}
