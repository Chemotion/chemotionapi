"""Unit tests for attachment edge cases (offline/pure).

Covers the behavior fix: MutableAttachments.add_file must raise a real
NotImplementedError (previously `raise NotImplemented` raised TypeError).
"""
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import requests

from chemotion_api.elements.attachments import Attachments, MutableAttachments


def test_mutable_attachments_add_file_raises_not_implemented_error():
    # con is only stored, not used by add_file; a sentinel object is enough.
    att = MutableAttachments(con=object(), attachment_data=None)
    with pytest.raises(NotImplementedError):
        att.add_file("whatever.txt")


@pytest.fixture
def _queued_attachments():
    """An Attachments container with a single file queued for upload (not yet saved).

    ``save()``/``_save_generic()`` reopen the file from disk, so it must still exist when the
    test calls save() -- only cleaned up once the test (and fixture teardown) is done.
    """
    con = MagicMock()
    atts = Attachments(con=con, attachment_data=None)
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"hello")
        tmp_path = f.name
    try:
        with patch("chemotion_api.elements.attachments.magic.Magic",
                   lambda mime=True: MagicMock(from_file=lambda p: "text/plain")):
            atts.add_file(tmp_path)
        yield atts, con
    finally:
        os.unlink(tmp_path)


def test_attachments_save_raises_and_keeps_queue_on_non_2xx_response(_queued_attachments):
    """Regression test for PR review finding 3: a failed (non-2xx) upload response must not be
    treated as success -- the upload queue must survive so a retried save() resends the files,
    and the caller must be told the save failed (a RequestException), not get a silent no-op."""
    atts, con = _queued_attachments
    assert len(atts._to_uploads) == 1
    assert len(atts._new_attachment_data) == 1

    bad_response = MagicMock()
    bad_response.status_code = 422
    bad_response.text = "Unprocessable Entity"
    con.post.return_value = bad_response

    with pytest.raises(requests.RequestException):
        atts.save(id=1, element_type='ResearchPlan')

    # Nothing should have moved into the "done" list, and the queue must still be intact.
    assert len(atts._attachment_data) == 0
    assert len(atts._to_uploads) == 1
    assert len(atts._new_attachment_data) == 1


def test_attachments_save_generic_raises_and_keeps_queue_on_non_2xx_response(_queued_attachments):
    """Same as above, for the 'Element' (generic) save path (_save_generic)."""
    atts, con = _queued_attachments

    bad_response = MagicMock()
    bad_response.status_code = 500
    bad_response.text = "Internal Server Error"
    con.post.return_value = bad_response

    with pytest.raises(requests.RequestException):
        atts.save(id=1, element_type='Element')

    assert len(atts._attachment_data) == 0
    assert len(atts._to_uploads) == 1
    assert len(atts._new_attachment_data) == 1


def test_attachments_save_marks_done_on_success_response(_queued_attachments):
    """Sanity check: a genuine 2xx response still clears the queue as before."""
    atts, con = _queued_attachments

    good_response = MagicMock()
    good_response.status_code = 201
    con.post.return_value = good_response

    res = atts.save(id=1, element_type='ResearchPlan')

    assert res is good_response
    assert len(atts._attachment_data) == 1
    assert len(atts._to_uploads) == 0
    assert len(atts._new_attachment_data) == 0
