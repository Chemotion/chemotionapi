"""The 'known defects, deliberately not fixed' list — now fixed.

Each was small, self-contained, and failed quietly rather than loudly. They had been recorded
during review passes whose standing instruction was "record, don't fix"; that rationale expired.
"""
import types

import pytest


# --- 1. crate file ids were keyed on Python object identity ------------------





# --- 3. a guard that vanished under `python -O` ------------------------------



# --- 4. a successful 204 upload was treated as a failure ---------------------

@pytest.mark.parametrize("status", [200, 201, 202, 204])
def test_any_2xx_upload_response_counts_as_success(status):
    """The gate accepted only 200/201, so a 204 No Content raised *after* the upload had already
    succeeded — and the retry then uploaded everything a second time."""
    from chemotion_api.elements.attachments import Attachments

    att = Attachments.__new__(Attachments)
    att._attachment_data, att._new_attachment_data, att._to_uploads = [], [], []
    att._raise_or_mark_done(types.SimpleNamespace(status_code=status, text=""))


@pytest.mark.parametrize("status", [400, 401, 500])
def test_non_2xx_still_raises_with_the_queue_intact(status):
    import requests

    from chemotion_api.elements.attachments import Attachments

    att = Attachments.__new__(Attachments)
    att._attachment_data, att._new_attachment_data = [], []
    att._to_uploads = [{"file_path": "a.txt", "file_uuid": "u"}]
    with pytest.raises(requests.RequestException):
        att._raise_or_mark_done(types.SimpleNamespace(status_code=status, text="no"))
    assert att._to_uploads, "the queue must survive so the save can be retried"


# --- 6. the 500 s read timeout was not configurable --------------------------

def test_connection_timeout_defaults_and_overrides():
    from chemotion_api.connection import Connection

    assert Connection("https://eln.example.org")._timeout == Connection.DEFAULT_TIMEOUT
    assert Connection("https://eln.example.org", timeout=(1, 5))._timeout == (1, 5)
    assert Connection("https://eln.example.org", timeout=30)._timeout == 30


def test_connection_timeout_reaches_the_request():
    from chemotion_api.connection import Connection

    con = Connection("https://eln.example.org", timeout=(1, 7))
    seen = {}
    con.request = lambda method, url=None, **kw: (
        seen.update(kw) or types.SimpleNamespace(status_code=200, headers={}))
    con._send_request("get", "/about", {}, {})
    assert seen["timeout"] == (1, 7)
    # an explicit per-call timeout still wins
    con._send_request("get", "/about", {}, {"timeout": (1, 2)})
    assert seen["timeout"] == (1, 2)
