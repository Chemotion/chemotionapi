"""Slice 8: wellplates are not all 12x8.

v4 accepts any width/height in 1..100. The client hardcoded 12 columns and rows A-H, so a larger
plate raised IndexError on load and `_clean_properties_data` walked every well, meaning even an
untouched save crashed.
"""
import copy

import pytest

from chemotion_api.elements.wellplate import (
    DEFAULT_HEIGHT, DEFAULT_WIDTH, MAX_DIMENSION, Wellplate, WellplateCol, row_label)


@pytest.mark.parametrize("index, label", [
    (0, "A"), (7, "H"), (25, "Z"),
    (26, "AA"), (51, "AZ"), (52, "BA"), (77, "BZ"), (78, "CA"), (99, "CV"), (103, "CZ"),
])
def test_row_label_matches_the_web_client(index, label):
    """Mirrors the literal table in the ELN's models/Wellplate.js; a divergence renames wells."""
    assert row_label(index) == label


def test_column_keys_follow_the_plate_height():
    assert list(WellplateCol()) == list("ABCDEFGH")
    assert list(WellplateCol(height=3)) == ["A", "B", "C"]
    assert list(WellplateCol(height=MAX_DIMENSION))[-1] == "CV"


def test_out_of_range_row_key_names_the_actual_range():
    col = WellplateCol(height=3)
    with pytest.raises(IndexError, match="row keys are A-C"):
        col["D"]


@pytest.fixture(autouse=True)
def _stub_sample(monkeypatch):
    """These tests are about which grid cell a well lands in, not about Sample construction.

    A real Sample builds a Connection and walks the generic-segment classes eagerly.
    """
    class _Sample:
        def __init__(self, _segments, _session, json_data):
            self.json_data = json_data

        def clean_data(self):
            return self.json_data

    monkeypatch.setattr("chemotion_api.elements.wellplate.Sample", _Sample)


def _plate(json_data):
    """A Wellplate over a fixed payload, with no server behind it."""
    wp = Wellplate.__new__(Wellplate)
    wp.json_data = json_data
    wp._wells = None
    wp._data_loaded = True        # _ensure_loaded() must not try to reach a server
    wp._is_partial = False        # built via __new__, so __init__ never set it
    wp._loading = False
    wp.is_new = False
    wp._id = 1                    # the `id` setter builds a json_ld @id from the session
    wp._generic_segments = None
    wp._session = None
    return wp


def _well(x, y, sample=None):
    return {"position": {"x": x, "y": y}, "sample": sample}


def test_defaults_when_the_server_omits_the_dimensions():
    wp = _plate({"wells": []})
    assert (wp.width, wp.height, wp.size) == (DEFAULT_WIDTH, DEFAULT_HEIGHT, 96)


def test_a_larger_plate_loads_instead_of_indexerror():
    """A 24x16 plate: column 23 and row P are both past the old hardcoded 12x8 grid."""
    wp = _plate({"width": 24, "height": 16,
                 "wells": [_well(24, 16, {"id": 9, "type": "sample"})]})
    assert (wp.width, wp.height, wp.size) == (24, 16, 384)
    assert len(wp.wells) == 24
    assert list(wp.wells[0])[-1] == "P"
    assert wp.wells[23]["P"] is not None


def test_a_100x100_plate_is_within_range():
    wp = _plate({"width": MAX_DIMENSION, "height": MAX_DIMENSION, "wells": []})
    assert len(wp.wells) == MAX_DIMENSION and len(wp.wells[0]) == MAX_DIMENSION


@pytest.mark.parametrize("value", [0, 101, -1, "12", None, True])
def test_out_of_range_dimensions_fall_back_to_the_default(value):
    assert _plate({"width": value, "wells": []}).width == DEFAULT_WIDTH


def test_a_well_outside_the_plate_is_skipped_not_fatal(caplog):
    wp = _plate({"width": 2, "height": 2,
                 "wells": [_well(99, 1, {"id": 1}), _well(1, 1, {"id": 2})]})
    with caplog.at_level("WARNING"):
        wells = wp.wells
    assert wells[0]["A"] is not None
    assert "outside this 2x2 plate" in caplog.text


@pytest.mark.parametrize("position", [None, {}, {"x": 1}, {"x": "a", "y": 1}, {"x": None, "y": 1}])
def test_an_unreadable_well_position_is_skipped(position, caplog):
    wp = _plate({"width": 2, "height": 2, "wells": [{"position": position, "sample": {"id": 1}}]})
    with caplog.at_level("WARNING"):
        assert all(s is None for col in wp.wells for s in col.values())
    assert "unreadable position" in caplog.text


def test_clean_properties_data_no_longer_slices_on_a_nonexistent_size_key():
    """`wells[:json_data.get('size')]` was always `[:None]`: `size` is a Rails *method*
    (width * height), not a column, and WellplateEntity never exposes it."""
    json_data = {"width": 2, "height": 2, "name": "P", "description": None,
                 "wells": [_well(1, 1), _well(2, 2)]}
    wp = _plate(json_data)
    wp._properties = {"name": "P", "description": None}
    out = wp._clean_properties_data()
    assert len(out["wells"]) == 2                      # nothing dropped
    assert all(w["is_new"] is False for w in out["wells"])
    assert all(w["sample"] is None for w in out["wells"])


def test_loading_a_plate_does_not_split_its_samples(monkeypatch):
    """Reading must not write. `__setitem__` splits, and `Sample.split()` calls `save()`.

    So merely loading a wellplate PUT every occupied sample and then held *new, unsaved* `…-NaN`
    subsamples instead of the ones actually on the plate — which a later save wrote back.
    """
    splits: list = []

    class _Sample:
        def __init__(self, _segments, _session, json_data):
            self.json_data = json_data

        def split(self):
            splits.append(self.json_data)
            return _Sample(None, None, {"short_label": "S-NaN", "is_new": True})

        def clean_data(self):
            return self.json_data

    monkeypatch.setattr("chemotion_api.elements.wellplate.Sample", _Sample)

    wp = _plate({"width": 2, "height": 2,
                 "wells": [_well(1, 1, {"id": 5, "short_label": "S-1"})]})
    placed = wp.wells[0]["A"]
    assert splits == []                                  # nothing was written to the server
    assert placed.json_data["short_label"] == "S-1"      # the real sample, not a -NaN split


def test_assigning_a_sample_to_a_well_still_splits_it(monkeypatch):
    """The ELN's semantics for putting a sample into a well; only the *parse* path changed."""
    class _Sample:
        def __init__(self, label):
            self.label = label

        def split(self):
            return _Sample(self.label + "-NaN")

    col = WellplateCol(height=2)
    col["A"] = _Sample("S-1")
    assert col["A"].label == "S-1-NaN"


def test_serialising_does_not_mutate_the_wellplate():
    """It wrote cleaned payloads into `json_data['wells'][i]['sample']` and returned `json_data`
    itself. `save()` only reloads on success, so after a failed PUT the in-memory element held
    serialised payloads where the server's raw records had been."""
    json_data = {"width": 2, "height": 2, "name": "P", "description": None,
                 "wells": [_well(1, 1, {"id": 5}), _well(2, 2)]}
    wp = _plate(json_data)
    wp._properties = {"name": "Renamed", "description": "d"}
    before = copy.deepcopy(json_data)

    out = wp._clean_properties_data()

    assert json_data == before, "the element must be unchanged by serialising it"
    assert out is not json_data
    assert out["name"] == "Renamed" and out["description"] == "d"
    assert out["wells"][0]["sample"] == {"id": 5}
    assert out["wells"][1]["sample"] is None
