"""A 2xx reply whose body says the request failed is raised as ChemotionRejectedError.

The ELN answers a refused create with 201 and ``{"errors": ...}``, a rescued exception with 200 and
``{"error": ...}``, and some routes with ``{"success": false}``. Each was read as success where a
method checked only the status code.
"""
import json
import unittest.mock as mock

import pytest
import requests

from chemotion_api.connection import ChemotionRejectedError, Connection


def _reply(body, status=201, content_type='application/json'):
    res = requests.Response()
    res.status_code = status
    res.headers['Content-Type'] = content_type
    res._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return res


def _send(res, **kwargs):
    conn = Connection('https://eln.example.org')
    with mock.patch.object(requests.Session, 'post', lambda self, **kw: res):
        return conn._send_request('post', '/api/v1/x', {}, kwargs)


@pytest.mark.parametrize('body', [
    {'errors': {'name': ['has already been taken']}},
    {'error': 'Validation failed: Name Please enter a name'},
    {'success': False, 'error': 'Failed to render SVG'},
    {'success': False},
])
def test_a_success_status_with_a_failure_body_raises(body):
    with pytest.raises(ChemotionRejectedError) as exc:
        _send(_reply(body))
    assert exc.value.body == body
    assert isinstance(exc.value, ValueError) and isinstance(exc.value, ConnectionError)


@pytest.mark.parametrize('body', [
    {'error': 0},                       # a public route's way of saying "no error"
    {'errors': []},                     # an import with nothing to report
    {'errors': {}},
    {'success': True, 'error': None},
    {'sample': {'id': 1, 'name': 'error analysis'}},
    [{'error': 'inside a list is data, not a reply status'}],
])
def test_a_success_body_passes(body):
    assert _send(_reply(body)).status_code == 201


def test_a_caller_that_reads_the_body_itself_can_opt_out():
    res = _reply({'errors': {'name': ['taken']}})
    assert _send(res, allow_error_body=True) is res


def test_non_json_and_error_statuses_are_left_alone():
    assert _send(_reply(b'{"error": "x"}', content_type='text/plain')).status_code == 201
    assert _send(_reply({'error': 'x'}, status=422)).status_code == 422
