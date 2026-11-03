"""Known defects in attachment identity and crate member handling."""
import types
import pytest


def test_file_id_survives_a_fresh_wrapper_object():
    """`{id(att): safe_name}` held only while every accessor returned the *same* wrapper object.
    A miss fell through to recomputing the name WITHOUT the disambiguation suffix, producing an
    `@id` pointing at a ZIP entry that does not exist — the exact failure the suffix prevents."""
    from chemotion_api.collection import _attachment_key

    original = {"identifier": "uuid-1", "filename": "spectrum.jdx"}
    # Same record, different dict object — what a re-fetch or a rebuilt wrapper produces.
    refetched = {"identifier": "uuid-1", "filename": "spectrum.jdx"}

    assert _attachment_key(original) == _attachment_key(refetched)
    assert id(original) != id(refetched)


def test_attachment_key_prefers_identifier_then_id_then_object_identity():
    from chemotion_api.collection import _attachment_key

    assert _attachment_key({"identifier": "u", "id": 3}) == "u"
    assert _attachment_key({"id": 3}) == 3
    bare = {"filename": "x.txt"}
    assert _attachment_key(bare) == id(bare)
    assert _attachment_key(object()) is not None          # not a mapping: must not raise


def test_member_size_guard_does_not_rely_on_assert():
    """`assert self._zip is not None` is stripped by -O, silencing the guard entirely."""
    from chemotion_api.offline.export_reader import ExportArchive

    archive = ExportArchive.__new__(ExportArchive)
    archive._zip = None
    with pytest.raises(RuntimeError, match="directory archive"):
        archive._check_member_size("anything")
