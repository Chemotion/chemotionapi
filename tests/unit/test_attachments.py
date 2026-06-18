"""Unit tests for attachment edge cases (offline/pure).

Covers the behavior fix: MutableAttachments.add_file must raise a real
NotImplementedError (previously `raise NotImplemented` raised TypeError).
"""
import pytest

from chemotion_api.elements.attachments import MutableAttachments


def test_mutable_attachments_add_file_raises_not_implemented_error():
    # con is only stored, not used by add_file; a sentinel object is enough.
    att = MutableAttachments(con=object(), attachment_data=None)
    with pytest.raises(NotImplementedError):
        att.add_file("whatever.txt")
