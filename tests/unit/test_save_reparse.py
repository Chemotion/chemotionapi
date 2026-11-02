"""The two missed instances of the slice-2 "iterate then save destroys gated fields" fix.

v4 gates `description`, `location`, `solvent`, `target_amount_*`, `real_amount_*`,
`boiling_point`, `melting_point`, `container`, `segments`, … behind `unless: :displayed_in_list`,
so a list payload carries nulls where the detail payload carries values. Slice 2 fixed this at the
`properties` accessor. Two paths reached `save()` without ever touching `properties`.
"""
import pytest

from chemotion_api.elements.abstract_element import AbstractElement

LIST_PAYLOAD = {"id": 1, "type": "sample", "name": "Original", "description": None,
                "location": None, "target_amount_value": None}
DETAIL_PAYLOAD = {"id": 1, "type": "sample", "name": "Original", "description": "Real notes",
                  "location": "Shelf B", "target_amount_value": 2.5}


class _Element:
    """Exercises the real `save()`/`load()`/`name` machinery over a scripted server."""

    save = AbstractElement.save
    load = AbstractElement.load
    properties = AbstractElement.properties
    name = AbstractElement.name
    _ensure_loaded = AbstractElement._ensure_loaded
    _load_if_partial = AbstractElement._load_if_partial
    on_properties_change = AbstractElement.on_properties_change

    def __init__(self, fail_detail_fetch=False):
        self.json_data = dict(LIST_PAYLOAD)
        self._properties = dict(LIST_PAYLOAD)
        self._name = LIST_PAYLOAD["name"]
        self._data_loaded = False
        self._is_partial = False
        self._loading = False
        self._load_failed = False
        self.is_new = False
        self._id = 1
        self._element_type = "sample"
        self._attachments = None
        self.attachments = None
        self.put_body = None
        self.detail_fetches = 0
        self.fail_detail_fetch = fail_detail_fetch

    id = property(lambda self: self._id)
    element_type = property(lambda self: self._element_type)
    analyses = property(lambda self: _NoAnalyses())

    def _load_data_from_server(self):
        self.detail_fetches += 1
        if self.fail_detail_fetch:
            raise ConnectionError("transient 500")
        return None, dict(DETAIL_PAYLOAD)

    def _set_json_data(self, json_data):
        self.json_data = dict(json_data)
        self._properties = dict(json_data)
        self._name = json_data.get("name", "")

    def clean_data(self):
        return dict(self._properties)

    def save_url(self):
        return "/api/v1/samples/1"

    @property
    def _session(self):
        element = self

        class _S:
            @staticmethod
            def put(url, data=None, **kw):
                element.put_body = data
                return type("R", (), {"status_code": 200, "json": staticmethod(dict)})()
        return _S()


class _NoAnalyses:
    def save_attachments(self):
        pass

    def clean_up_after_save(self):
        pass


def test_bare_save_reparses_the_refetched_payload():
    """`self.json_data = json_data` refreshed the raw dict but left `_properties` list-derived,
    then set `_data_loaded = True` so the accessor fix could never fire. A plain
    `for s in col.get_samples(): s.save()` PUT nulls over description/location/target_amount."""
    import json

    el = _Element()
    el.save()
    body = json.loads(el.put_body)
    assert body["description"] == "Real notes"
    assert body["location"] == "Shelf B"
    assert body["target_amount_value"] == 2.5


def test_renaming_loads_before_it_edits():
    """The `name` setter wrote to `_properties` without ever triggering the load, so the most
    obvious bulk edit there is — renaming — never fetched the gated fields."""
    import json

    el = _Element()
    el.name = "Renamed"
    assert el.detail_fetches == 1          # the setter loaded first
    el.save()
    body = json.loads(el.put_body)
    assert body["name"] == "Renamed"       # the edit survived the reparse
    assert body["description"] == "Real notes"


def test_a_failed_load_does_not_pin_the_element_as_loaded():
    """`load()` set `_data_loaded = True` *before* the request, and `_ensure_loaded` swallows the
    exception — so one transient 500 pinned the element to its list-derived properties for good,
    and the next save PUT those nulls back."""
    el = _Element(fail_detail_fetch=True)
    el._ensure_loaded()                    # swallows the error, by design
    assert el._data_loaded is False        # but must not claim the element is loaded

    # Automatic retry on every subsequent access is deliberately NOT the recovery mechanism —
    # see test_a_failing_load_is_attempted_once_not_on_every_access. What matters here is that
    # `save()` cannot mistake this element for a loaded one; see
    # test_save_still_refuses_to_write_when_the_refetch_fails.
    assert el._load_failed is True


def test_load_still_guards_against_reentrancy():
    """`_data_loaded` is set before the request on purpose: `_set_json_data` walks `properties`."""
    el = _Element()
    el.load()
    assert el.detail_fetches == 1


def test_a_failing_load_is_attempted_once_not_on_every_access(caplog):
    """Not marking the element loaded must not turn into a retry storm: an offline element whose
    detail fetch always 404s was re-attempted on every single property access (50+ identical
    warnings for one `to_dcat_ap()` call)."""
    el = _Element(fail_detail_fetch=True)
    with caplog.at_level("WARNING"):
        for _ in range(10):
            el.properties            # noqa: B018 - the access is the point
    assert el.detail_fetches == 1
    assert sum("Could not load the full record" in r.message for r in caplog.records) == 1
    assert el._data_loaded is False  # still not claiming to be loaded


def test_an_explicit_load_can_still_recover_after_a_failure():
    el = _Element(fail_detail_fetch=True)
    el._ensure_loaded()
    el.fail_detail_fetch = False
    el.load()                        # explicit retry
    assert el._load_failed is False and el._data_loaded is True
    assert el.properties["description"] == "Real notes"


def test_save_still_refuses_to_write_when_the_refetch_fails():
    """The point of not marking a failed load as loaded: `save()` re-fetches through its own path
    and must raise, rather than PUT the list-derived nulls."""
    el = _Element(fail_detail_fetch=True)
    el._ensure_loaded()              # sets _load_failed, leaves _data_loaded False
    with pytest.raises(ConnectionError):
        el.save()
    assert el.put_body is None
