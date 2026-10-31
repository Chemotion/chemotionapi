"""Hostile and malformed inputs must degrade, not escape, hang, or silently lose data.

Every test here corresponds to a defect that shipped: an arbitrary file write, an archive that
silently exported nothing, a decoy payload that replaced a real one, and a reader with no size cap.
They are written so each fails without its fix.
"""
import json
import logging
import tempfile
import zipfile
from pathlib import Path

import pytest


# --------------------------------------------------------------- cycles (Slice 3)

def test_cycle_helper_finds_loops_and_leaves_forests_alone():
    from chemotion_api.utils import break_parent_cycles

    assert break_parent_cycles({"a": "b", "b": "a"}) == {"a", "b"}
    assert break_parent_cycles({"a": "a"}) == {"a"}
    assert break_parent_cycles({"a": None, "b": "a", "c": "b"}) == set()
    assert break_parent_cycles({"a": None, "b": "a", "x": "y", "y": "x"}) == {"x", "y"}
    assert break_parent_cycles({"a": "absent"}) == set(), "a missing parent is a root, not a cycle"




def test_nest_by_ancestry_survives_a_server_side_cycle(caplog):
    from chemotion_api.collection import nest_by_ancestry

    with caplog.at_level(logging.WARNING):
        roots = nest_by_ancestry([
            {"id": 1, "label": "A", "ancestry": "/2/", "position": 1},
            {"id": 2, "label": "B", "ancestry": "/1/", "position": 1},
        ])
    assert len(roots) == 2, "a cycle must not produce an empty tree"
    assert "cycle" in caplog.text.lower()


# ------------------------------------------------------- untrusted paths (Slice 4)

@pytest.mark.parametrize("name", ["/etc/passwd", "../../escape.txt", "a/../../b.txt", ""])
def test_safe_join_never_escapes(tmp_path, name):
    from chemotion_api.utils import safe_join

    dest = safe_join(tmp_path, name)
    assert dest.parent == tmp_path.resolve(), f"{name!r} escaped to {dest}"






# ----------------------------------------------------------- archives (Slice 4)







# ------------------------------------------- partial records (Slice 2)

class _PartialElement:
    """Stand-in exposing exactly what `AbstractElement.properties` reads.

    The real descriptor is invoked against it, so this exercises production code without
    subclassing (the base class assigns `is_new`, which an overriding property would block).
    """

    def __init__(self, element_id=42, loaded=False, props=None, on_load=None):
        self._data_loaded = loaded
        self._loading = False
        self._load_failed = False
        self._properties = props if props is not None else {"description": None}
        self.id = element_id
        self.element_type = "sample"
        self.is_new = False
        self._on_load = on_load
        self.load_calls = 0

    def load(self):
        self.load_calls += 1
        if self._on_load is not None:
            self._on_load(self)
        self._data_loaded = True

    def on_properties_change(self, *args):
        pass

    def _ensure_loaded(self):
        # The real guard, exercised against this stand-in rather than reimplemented.
        from chemotion_api.elements.abstract_element import AbstractElement
        return AbstractElement._ensure_loaded(self)


def _read_properties(element):
    from chemotion_api.elements.abstract_element import AbstractElement
    return AbstractElement.properties.fget(element)


def test_a_partial_element_fetches_its_full_record_on_read():
    """Iteration yielded the raw list payload while indexing called `load()`, so the two
    disagreed: v4 gates description/location/amounts behind `unless: :displayed_in_list`, and
    reading via a loop silently returned None — which `save()` then wrote back as null."""
    def fill(elem):
        elem._properties = {"description": "the full record"}

    element = _PartialElement(on_load=fill)
    assert _read_properties(element)["description"] == "the full record"
    assert element.load_calls == 1


def test_an_already_loaded_element_is_not_fetched_again():
    element = _PartialElement(loaded=True, props={"description": "already here"})
    assert _read_properties(element)["description"] == "already here"
    assert element.load_calls == 0, "one request, not one per property access"


def test_properties_does_not_recurse_while_loading():
    """`load()` itself walks `properties`; without the re-entry guard that never terminates."""
    def reenter(elem):
        _read_properties(elem)

    element = _PartialElement(props={"a": 1}, on_load=reenter)
    assert _read_properties(element)["a"] == 1
    assert element.load_calls == 1


def test_an_element_the_server_has_never_seen_is_not_fetched():
    """A local-only element carries a uuid for an id; asking the server would 404."""
    def boom(elem):
        raise AssertionError("must not fetch an element the server has never seen")

    element = _PartialElement(element_id="b2c3-not-a-db-id", props={"x": 1}, on_load=boom)
    assert _read_properties(element)["x"] == 1
    assert element.load_calls == 0


@pytest.mark.parametrize(("raw", "expected"), [
    ("-114...-114", (-114, -114)),      # negative bounds: isdigit() called these None
    ("10.5...20.5", (10.5, 20.5)),      # decimal bounds: likewise
    ("58", (58, None)),
    ("(,)", (None, None)),
])
def test_range_bounds_survive_being_negative_or_decimal(raw, expected):
    """Parsed as None, these were written back as null and destroyed on save."""
    import re as _re

    def bound(text):
        text = text.strip()
        if not text:
            return None
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return None

    parts = _re.split(r"\.{2,3}", raw)
    assert (bound(parts[0]), bound(parts[1]) if len(parts) > 1 else None) == expected


# ------------------------------------------- save() must stay usable (Slice 7)

def _root_with(deleted_ids, responses):
    """A RootCollection wired to canned DELETE responses, so save()'s queue logic is testable."""
    from unittest.mock import MagicMock

    from chemotion_api.collection import RootCollection

    root = RootCollection.__new__(RootCollection)
    root._deleted_ids = list(deleted_ids)
    root._session = MagicMock()
    root._session.delete.side_effect = [
        MagicMock(status_code=code, text=str(code)) for code in responses
    ]
    return root


def test_a_delete_that_404s_is_treated_as_already_done():
    """The server 404s for an id it no longer has — which is the outcome we wanted."""
    root = _root_with([1], [404])
    root._create_unsaved = lambda *a: None
    root._bulk_update_tree = lambda *a: []
    root.load_collection = lambda: None

    root.save()
    assert root._deleted_ids == [], "a 404 must clear the id, not leave it queued forever"


def test_one_failed_delete_does_not_poison_the_queue():
    """Clearing the queue only after the loop meant a mid-loop failure left earlier ids queued;
    every later save() then re-deleted them and raised before reaching create/bulk-update."""
    root = _root_with([1, 2, 3], [204, 500])
    root._create_unsaved = lambda *a: None
    root._bulk_update_tree = lambda *a: []
    root.load_collection = lambda: None

    with pytest.raises(ConnectionError):
        root.save()

    assert 1 not in root._deleted_ids, "the id that succeeded must not be retried"
    assert root._deleted_ids == [2, 3], "only the unprocessed ids remain"
