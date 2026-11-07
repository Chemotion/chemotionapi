"""User labels, completed (M1.6): bulk add/remove, saving labels, labels on every element type."""
import json
import os

import pytest

from chemotion_api.collection import Collection
from chemotion_api.user import User, UserLabel


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res):
        self.res, self.calls, self.labels_reset = res, [], 0

    def post(self, url, data=None, **kw):
        self.calls.append(('post', url, data))
        return self.res

    def put(self, url, data=None, **kw):
        self.calls.append(('put', url, data))
        return self.res

    def reset_user_labels(self):
        self.labels_reset += 1


class _El:
    def __init__(self, kind, elem_id):
        self.element_type, self.id, self.is_new = kind, elem_id, False


def _collection(session, col_id=11):
    col = Collection.__new__(Collection)
    col._id, col.label = col_id, 'Source'
    root = type('_Root', (), {'_session': session})()
    col.get_root = lambda: root
    return col


def test_bulk_selects_each_element_and_sends_label_ids():
    session = _Session(_Res(204))
    _collection(session).update_user_labels(_El('sample', 1), _El('screen', 2), _El('my_generic', 3),
                                            add=[UserLabel(id=5), 6], remove=[7])
    (_, url, body), = session.calls
    assert url == '/api/v1/user_labels/bulk'
    assert body['add_label_ids'] == [5, 6] and body['remove_label_ids'] == [7]
    assert body['ui_state']['currentCollection'] == {'id': 11}
    assert body['ui_state']['screen'] == {'checkedAll': False, 'checkedIds': [2]}
    assert body['ui_state']['my_generic'] == {'checkedAll': False, 'checkedIds': [3]}


@pytest.mark.parametrize('kwargs, match', [
    ({}, 'labels to add or remove'),
    ({'add': ['nope']}, 'Not a user label'),
    ({'add': [True]}, 'Not a user label'),
    ({'add': [UserLabel()]}, 'Not a user label'),
])
def test_bad_label_arguments_send_nothing(kwargs, match):
    session = _Session(_Res(204))
    with pytest.raises(ValueError, match=match):
        _collection(session).update_user_labels(_El('sample', 1), **kwargs)
    assert session.calls == []


def test_no_elements_or_unsaved_ones_send_nothing():
    session = _Session(_Res(204))
    with pytest.raises(ValueError, match='No elements'):
        _collection(session).update_user_labels(add=[1])
    with pytest.raises(ValueError, match='not been saved'):
        _collection(session).update_user_labels(_El('sample', None), add=[1])
    assert session.calls == []


@pytest.mark.parametrize('status', [401, 403])
def test_refusals_are_permission_errors(status):
    with pytest.raises(PermissionError):
        _collection(_Session(_Res(status, 'No accessible labels'))).update_user_labels(_El('sample', 1), add=[1])


def _user(session):
    user = User.__new__(User)
    user._session = session
    return user


def test_saving_a_new_label_omits_the_id_and_drops_the_cache():
    stored = {'id': 9, 'user_id': 7, 'access_level': 0, 'title': 't', 'description': None, 'color': '#f00'}
    session = _Session(_Res(200, stored))
    label = _user(session).save_user_label(UserLabel(title='t', color='#f00'))
    (_, url, body), = session.calls
    assert url == '/api/v1/user_labels/save_label'
    assert body == {'title': 't', 'color': '#f00'}
    assert label.id == 9 and session.labels_reset == 1


def test_saving_someone_elses_label_is_a_permission_error():
    with pytest.raises(PermissionError, match='not one of yours'):
        _user(_Session(_Res(404))).save_user_label(UserLabel(id=3, title='t'))


def test_a_label_needs_a_title():
    session = _Session(_Res(200))
    with pytest.raises(ValueError, match='title'):
        _user(session).save_user_label(UserLabel(color='#f00'))
    assert session.calls == []


def test_screen_wellplate_and_research_plan_round_trip_user_labels():
    from chemotion_api.elements.research_plan import ResearchPlan
    from chemotion_api.elements.screen import Screen
    from chemotion_api.elements.wellplate import Wellplate
    from chemotion_api.schema_manager import SchemaManager

    class _About:
        status_code, text = 200, '<h4>Version: v4.0.0</h4>'

    session = type('_S', (), {'schema_manager': SchemaManager(_About()), '_host_url': 'http://x'})()
    segments = type('_Seg', (), {'all_classes': []})()
    with open(os.path.join(os.path.dirname(__file__), 'data', 'screen_v4_main.json')) as f:
        screen_json = json.load(f)
    screen_json['user_labels'] = [4]
    plate_json = dict(screen_json['wellplates'][0], user_labels=[4])
    plan_json = dict(screen_json['research_plans'][0], user_labels=[4])

    for cls, payload in [(Screen, screen_json), (Wellplate, plate_json), (ResearchPlan, plan_json)]:
        element = cls(segments, session, json_data=payload)
        assert element.properties['user_labels'] == [4], cls.__name__
        element.properties['user_labels'] = [4, 8]
        assert element.clean_data()['user_labels'] == [4, 8], cls.__name__
