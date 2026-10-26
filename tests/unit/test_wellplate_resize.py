"""Resizing a wellplate on ELN v4.

v4 removed `width`/`height` from the ordinary wellplate PUT: the params block does not declare
them, so Grape drops them and assigning the attributes then calling `save()` is silently a no-op.
Upstream did that on purpose — otherwise a stale tab could revert someone else's resize. The only
route that changes the grid is `PUT /api/v1/wellplates/resize/:id`.
"""
import pytest

from chemotion_api.elements.wellplate import MAX_DIMENSION, Wellplate


class _Res:
    def __init__(self, status, payload=None, text="nope"):
        self.status_code, self._payload, self.text = status, payload, text
        self.content = b"x" if payload is not None else b""

    def json(self):
        return self._payload


class _GenericSegments:
    """Segment parsing walks this; an empty klass list is the "no generic segments" case."""
    all_classes: list = []


class _SchemaManager:
    """`_set_json_data` rebuilds the element's JSON-LD @type through this."""

    @staticmethod
    def generate_model_type(element_type, schema_version=None):
        return f"chemotion:type/{element_type}/4.0"


class _Session:
    def __init__(self, res):
        self.calls, self._res = [], res
        self.schema_manager = _SchemaManager()
        self._host_url = "https://eln.example.org"     # the id setter rebuilds json_ld['@id']

    def put(self, url, data=None, **kwargs):
        self.calls.append((url, data))
        return self._res


def _plate(session):
    wp = Wellplate.__new__(Wellplate)
    wp.json_data = {"width": 12, "height": 8, "wells": []}
    wp._wells = None
    wp._data_loaded = True
    wp._is_partial = False   # built via __new__, so __init__ never set it
    wp._loading = False
    wp.is_new = False
    wp._id = 5
    wp._generic_segments = _GenericSegments()
    wp._session = session
    wp._properties = {}          # _set_json_data re-parses into this on refresh
    wp._load_failed = False
    wp.json_ld = {}
    wp._element_type = "wellplate"
    return wp


def test_resize_posts_to_the_dedicated_route():
    session = _Session(_Res(200, {"wellplate": {"width": 24, "height": 16, "wells": []}}))
    plate = _plate(session)
    plate.resize(24, 16)
    assert session.calls == [("/api/v1/wellplates/resize/5",
                              {"id": 5, "width": 24, "height": 16})]


def test_resize_refreshes_the_grid_from_the_response():
    session = _Session(_Res(200, {"wellplate": {"width": 24, "height": 16, "wells": []}}))
    plate = _plate(session)
    plate.resize(24, 16)
    assert (plate.width, plate.height) == (24, 16)
    assert len(plate.wells) == 24           # the parsed columns were rebuilt, not stale


@pytest.mark.parametrize("width, height", [(-1, 8), (12, -1), (MAX_DIMENSION + 1, 8),
                                           (12, MAX_DIMENSION + 1), (True, 8), ("12", 8), (1.5, 8)])
def test_out_of_range_dimensions_never_reach_the_server(width, height):
    session = _Session(_Res(200, {}))
    with pytest.raises(ValueError):
        _plate(session).resize(width, height)
    assert session.calls == []


def test_a_refused_shrink_surfaces_the_blocking_wells():
    """422 names the wells that still hold data. That text is the actionable part, so it must not
    be swallowed — and this client deliberately does not clear them to force the resize through."""
    session = _Session(_Res(422, text="Cannot shrink: wells C3, D4 hold data"))
    with pytest.raises(ValueError, match="C3, D4"):
        _plate(session).resize(2, 2)


@pytest.mark.parametrize("status, exc", [(401, PermissionError), (404, ValueError),
                                         (500, ConnectionError)])
def test_resize_maps_the_documented_failures(status, exc):
    with pytest.raises(exc):
        _plate(_Session(_Res(status))).resize(24, 16)
