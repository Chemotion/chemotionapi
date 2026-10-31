"""Attachments are identified by their record, not by their filename.

An element's own attachments plus every dataset of every analysis are collected together, and
those are distinct records. Deduplicating them on filename dropped real files from the crate.
"""
from chemotion_api.collection import _CrateFileNamer


def _names(attachments):
    namer = _CrateFileNamer()
    for att in attachments:
        namer.add(att)
    return [name for _att, name in namer.files]


def test_same_filename_on_two_records_keeps_both():
    """Two analyses each holding `spectrum.jdx` are two different files. Keying on the filename
    dropped the second one's bytes AND its File node — and appended nothing to `skipped`, so the
    crate did not even declare the omission."""
    names = _names([{"identifier": "aaa", "filename": "spectrum.jdx"},
                    {"identifier": "bbb", "filename": "spectrum.jdx"}])
    assert names == ["spectrum.jdx", "spectrum_2.jdx"]


def test_the_same_record_added_twice_is_still_deduplicated():
    att = {"identifier": "aaa", "filename": "spectrum.jdx"}
    assert _names([att, att]) == ["spectrum.jdx"]


def test_id_is_used_when_there_is_no_identifier():
    assert _names([{"id": 1, "filename": "a.txt"}, {"id": 1, "filename": "a.txt"}]) == ["a.txt"]
    assert len(_names([{"id": 1, "filename": "a.txt"}, {"id": 2, "filename": "a.txt"}])) == 2


def test_records_with_no_identity_fall_back_to_the_filename():
    """Without an identifier there is nothing else to go on, so the old behaviour is kept."""
    assert _names([{"filename": "a.txt"}, {"filename": "a.txt"}]) == ["a.txt"]


def test_different_names_that_sanitize_alike_are_disambiguated():
    names = _names([{"identifier": "a", "filename": "a b.txt"},
                    {"identifier": "b", "filename": "a/b.txt"}])
    assert len(names) == 2 and names[0] != names[1]


def test_disambiguation_keeps_counting_past_two():
    names = _names([{"identifier": str(i), "filename": "same.txt"} for i in range(4)])
    assert names == ["same.txt", "same_2.txt", "same_3.txt", "same_4.txt"]
