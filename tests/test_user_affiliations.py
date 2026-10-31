"""Offline tests for User.get_affiliations().

These paths are thin wrappers over single endpoints, so they are covered with a stubbed
connection rather than a live server — which is also how `Instance.get_affiliations()` managed to
ship broken: it delegated to a `User.get_affiliations()` that did not exist, and nothing called it.
"""
from unittest.mock import MagicMock

import pytest

from chemotion_api.user import Affiliation, Person


def _response(status_code=200, payload=None):
    res = MagicMock()
    res.status_code = status_code
    res.json.return_value = payload
    res.text = str(payload)
    return res


def _user_with(response):
    session = MagicMock()
    session.get.return_value = response
    return Person(session), session


AFFILIATION_ROWS = [
    {'id': 7, 'organization': 'Karlsruhe Institute of Technology', 'department': 'IBCS',
     'group': 'ComPlat', 'country': 'Germany', 'from': '2020-01-01', 'to': None},
    {'id': 8, 'organization': 'TU Braunschweig', 'department': None,
     'group': None, 'country': 'Germany', 'from': None, 'to': None},
]


def test_get_affiliations_parses_the_bare_array():
    """GET /api/v1/affiliations returns a bare JSON array — no root key to unwrap."""
    user, session = _user_with(_response(200, AFFILIATION_ROWS))

    affiliations = user.get_affiliations()

    session.get.assert_called_once_with('/api/v1/affiliations')
    assert [a.id for a in affiliations] == [7, 8]
    assert isinstance(affiliations[0], Affiliation)
    assert affiliations[0].organization == 'Karlsruhe Institute of Technology'
    assert affiliations[0].from_date == '2020-01-01'   # 'from' on the wire
    assert affiliations[0].raw is AFFILIATION_ROWS[0]  # untouched payload kept


def test_get_affiliations_name_joins_the_finer_units():
    user, _ = _user_with(_response(200, AFFILIATION_ROWS))
    first, second = user.get_affiliations()
    assert first.name == 'Karlsruhe Institute of Technology, IBCS, ComPlat'
    assert second.name == 'TU Braunschweig'


def test_get_affiliations_round_trips_through_to_dict():
    user, _ = _user_with(_response(200, AFFILIATION_ROWS))
    assert user.get_affiliations()[0].to_dict() == AFFILIATION_ROWS[0]


def test_get_affiliations_raises_permission_error_when_not_logged_in():
    user, _ = _user_with(_response(401))
    with pytest.raises(PermissionError):
        user.get_affiliations()


def test_get_affiliations_raises_connection_error_on_other_failures():
    user, _ = _user_with(_response(500))
    with pytest.raises(ConnectionError):
        user.get_affiliations()


