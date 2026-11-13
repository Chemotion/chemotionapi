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
    payload = _payload('wellplate') | {'is_restricted': False, 'name': '***',
                                       'description': {'ops': [{'insert': 'x'}]}}
    w = _element(Wellplate, payload)
    assert not w.is_restricted
    assert w.properties['name'] == '***'


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


# --- every built-in element type validates its properties (owner, 2026-11-13) --------------

def _wellplate():
    return _element(Wellplate, _payload('wellplate') | {'is_restricted': False, 'name': 'W',
                                                        'description': {'ops': [{'insert': 'x\n'}]}})


def test_wellplate_writes_are_validated():
    from pydantic import ValidationError
    w = _wellplate()
    with pytest.raises(ValidationError):
        w.properties['name'] = ['a list']
    w.properties['name'] = 'renamed'
    assert w.properties['name'] == 'renamed'


# --- rich text: plain strings or deltas, plus public helpers (owner, 2026-11-13) ----------

def test_text_to_quill_round_trips_with_quill_to_text():
    from chemotion_api import quill_to_text, text_to_quill
    delta = text_to_quill('kept cold')
    assert delta == {'ops': [{'insert': 'kept cold\n'}]}
    assert quill_to_text(delta) == 'kept cold'
    assert text_to_quill('two\nlines\n') == {'ops': [{'insert': 'two\nlines\n'}]}
    with pytest.raises(TypeError):
        text_to_quill(42)


def test_a_plain_string_is_stored_as_a_delta():
    w = _wellplate()
    w.properties['description'] = 'kept cold'
    assert w.properties['description'] == {'ops': [{'insert': 'kept cold\n'}]}


def test_a_formatted_delta_read_from_the_eln_can_be_written_back():
    w = _wellplate()
    rich = {'ops': [{'insert': 'Title'}, {'insert': '\n', 'attributes': {'header': 2}},
                    {'insert': {'image': 'data:...'}}, {'insert': '\n'}]}
    w.properties['description'] = rich
    assert w.properties['description'] == rich


@pytest.mark.parametrize("value", [42, {'ops': 'x'}, {'nope': []},
                                   {'ops': [{'retain': 3}]}, {'ops': [{'insert': 1}]}])
def test_a_malformed_value_is_refused(value):
    w = _wellplate()
    with pytest.raises(ValueError, match="rich text"):
        w.properties['description'] = value


def test_a_write_into_the_delta_must_leave_a_delta():
    w = _wellplate()
    w.properties['description']['ops'] = [{'insert': 'replaced\n'}]
    assert w.properties['description'] == {'ops': [{'insert': 'replaced\n'}]}
    with pytest.raises(ValueError, match="no longer be a Quill delta"):
        w.properties['description']['ops'] = 'not a list'


def test_reaction_description_and_observation_are_rich_text():
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from test_sample_properties import _reaction
    r = _reaction([])
    r.properties['observation'] = 'turned yellow'
    assert r.properties['observation'] == {'ops': [{'insert': 'turned yellow\n'}]}
    with pytest.raises(ValueError, match="rich text"):
        r.properties['description'] = {'ops': [{'insert': 1}]}


def test_a_restricted_payload_still_serialises_as_the_server_sent_it():
    """Downstream apps JSON-encode json_data (ChemAssistent's runner does); the sentinel is a str
    reading '***', so that keeps working (owner, 2026-11-13)."""
    import json as _json
    s = _element(Sample, _payload('sample'))
    assert s.properties['description'] is WITHHELD
    encoded = _json.loads(_json.dumps(s.json_data))
    assert encoded['description'] == '***'
    assert str(WITHHELD) == '***' and f'{WITHHELD}' == '***'
    with pytest.raises(WithheldValueError):
        WITHHELD + 'x'
    with pytest.raises(WithheldValueError):
        3 + WITHHELD
