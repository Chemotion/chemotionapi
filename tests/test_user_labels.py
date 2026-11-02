"""Offline tests for user labels: the UserLabel type, the connection cache, and
resolving an element's label ids to titles."""
from unittest.mock import MagicMock

import pytest

from chemotion_api.user import UserLabel


def _response(status_code=200, payload=None):
    res = MagicMock()
    res.status_code = status_code
    res.json.return_value = payload
    res.text = str(payload)
    return res


def _user_with(response):
    from chemotion_api.user import Person
    session = MagicMock()
    session.get.return_value = response
    return Person(session), session


LABEL_ROWS = [
    {'id': 3, 'user_id': 12, 'access_level': 0, 'title': 'for publication',
     'description': None, 'color': '#2196f3'},
    {'id': 5, 'user_id': 99, 'access_level': 1, 'title': 'shared',
     'description': 'visible to everyone', 'color': '#f44336'},
]


def test_get_user_labels_parses_the_labels_root():
    """GET list_labels wraps the array in a `labels` root key."""
    user, session = _user_with(_response(200, {'labels': LABEL_ROWS}))
    session.user_labels = LABEL_ROWS   # the connection-level cache the user object reads

    labels = user.get_user_labels()

    assert [(lbl.id, lbl.title) for lbl in labels] == [(3, 'for publication'), (5, 'shared')]
    assert labels[0].is_shared is False   # access_level 0 -> private
    assert labels[1].is_shared is True    # access_level 1 -> shared


def test_user_label_placeholder_reads_safely():
    """An unresolvable id must not blow up a join — that is what display_title is for."""
    unknown = UserLabel(id=42)
    assert unknown.title is None
    assert unknown.is_resolved is False
    assert unknown.display_title == '#42'
    assert ', '.join(lbl.display_title for lbl in [UserLabel.from_json(LABEL_ROWS[0]), unknown]) \
        == 'for publication, #42'


# --------------------------------------------------------------- connection cache behaviour

def _connection_with(payload, status_code=200):
    from chemotion_api.connection import Connection
    conn = Connection('https://example.invalid')
    conn.get = MagicMock(return_value=_response(status_code, payload))
    return conn


def test_user_labels_are_fetched_once_per_connection():
    """Resolving labels across many elements must not scale the request count."""
    conn = _connection_with({'labels': LABEL_ROWS})
    for _ in range(50):
        assert conn.user_labels == LABEL_ROWS
    assert conn.get.call_count == 1


def test_changing_the_bearer_token_drops_the_cached_labels():
    """The server filters labels by current user: serving user A's private labels to user B
    after a re-login would be a cross-user leak, not just staleness."""
    conn = _connection_with({'labels': LABEL_ROWS})
    conn.set_bearer_token('token-for-user-a')
    assert conn.user_labels == LABEL_ROWS
    assert conn.get.call_count == 1

    conn.set_bearer_token('token-for-user-b')
    assert conn.user_labels == LABEL_ROWS
    assert conn.get.call_count == 2, 'cache survived a token change'

    conn.reset_bearer_token()
    conn.user_labels
    assert conn.get.call_count == 3, 'cache survived a token reset'


def test_user_labels_raise_permission_error_when_not_logged_in():
    conn = _connection_with(None, status_code=401)
    with pytest.raises(PermissionError):
        conn.user_labels


def test_empty_label_list_is_not_refetched_every_time():
    """`labels: []` is a real answer, not a cache miss."""
    conn = _connection_with({'labels': []})
    assert conn.user_labels == []
    assert conn.user_labels == []
    assert conn.get.call_count == 1


# ------------------------------------------------- resolving labels on an element

class _StubElement:
    """Minimal stand-in that goes through the REAL `properties` descriptor.

    It used to expose a bare `_properties` dict, which meant the test could not notice that
    `user_labels_resolved` was reading `_properties` directly and so skipping the lazy fetch that
    `properties` performs — an element that had not been loaded reported no labels at all.
    """
    from chemotion_api.elements.abstract_element import AbstractElement

    properties = AbstractElement.properties
    _ensure_loaded = AbstractElement._ensure_loaded
    on_properties_change = AbstractElement.on_properties_change

    def __init__(self, session, label_ids, data_loaded=True):
        self._session = session
        self._properties = {'user_labels': label_ids}
        self._data_loaded = data_loaded
        self._loading = False
        self._load_failed = False
        self.is_new = False
        self._id = 1
        self._element_type = 'sample'

    @property
    def id(self):
        return self._id

    @property
    def element_type(self):
        return self._element_type

    def load(self):
        """Stand in for the server fetch: fill in the gated field a list payload omits."""
        self._properties = {'user_labels': [3, 5], 'description': 'loaded'}
        self._data_loaded = True


def _resolve(label_ids, rows=LABEL_ROWS):
    from chemotion_api.elements.abstract_element import AbstractElement
    session = MagicMock()
    session.user_labels = rows
    element = _StubElement(session, label_ids)
    return AbstractElement.user_labels_resolved.fget(element), session


def test_element_resolves_ids_to_titles():
    resolved, _ = _resolve([3, 5])
    assert [lbl.title for lbl in resolved] == ['for publication', 'shared']


def test_element_preserves_the_elements_own_order():
    resolved, _ = _resolve([5, 3])
    assert [lbl.id for lbl in resolved] == [5, 3]


def test_element_with_an_unresolvable_id_does_not_raise():
    """A label owned by another user is filtered out by `my_labels` server-side."""
    resolved, _ = _resolve([3, 777])
    assert len(resolved) == 2, 'one entry per id, always'
    assert resolved[1].id == 777
    assert resolved[1].is_resolved is False
    assert resolved[1].display_title == '#777'


def test_element_without_labels_makes_no_request():
    resolved, session = _resolve([])
    assert resolved == []
    assert not session.method_calls


def test_resolving_does_not_mutate_the_raw_id_list():
    """Acceptance: a sample fetched, resolved and saved unchanged keeps the same ids on the wire."""
    from chemotion_api.elements.abstract_element import AbstractElement
    session = MagicMock()
    session.user_labels = LABEL_ROWS
    element = _StubElement(session, [3, 5, 777])
    before = list(element._properties['user_labels'])

    AbstractElement.user_labels_resolved.fget(element)

    assert element._properties['user_labels'] == before
    assert all(isinstance(i, int) for i in element._properties['user_labels'])


def test_element_labels_trigger_the_lazy_load_like_properties_does():
    """Reading `_properties` directly skipped the fetch `properties` performs, so a not-yet-loaded
    element (one obtained by iterating a collection) reported no labels at all."""
    from chemotion_api.elements.abstract_element import AbstractElement

    session = MagicMock()
    session.user_labels = LABEL_ROWS
    element = _StubElement(session, [], data_loaded=False)   # list payload: no labels visible yet
    resolved = AbstractElement.user_labels_resolved.fget(element)
    assert [lbl.id for lbl in resolved] == [3, 5]
    assert element._data_loaded is True
