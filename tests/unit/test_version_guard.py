"""Offline tests for ELN version detection and the v4 compatibility gate.

No server needed: /about is a plain HTML page, so a fake response is enough.
"""
import pytest

from chemotion_api.schema_manager import (
    SUPPORTED_ELN_MAJOR,
    SchemaManager,
    UnsupportedServerVersion,
)


class _FakeResponse:
    """Minimal stand-in for the requests.Response that SchemaManager reads."""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


def _about(version: str) -> _FakeResponse:
    """An /about page rendered the way app/views/pages/about.haml does."""
    return _FakeResponse(
        "<div class='container my-5'><h1>Chemotion ELN - About</h1>"
        f"<h4>Version: {version}</h4>"
        "<h4>Base revision: f9541b4e21</h4>"
        "<h4>Current revision: 21ac3df593d0e549ca72faf54e5fa889b6e3f45d</h4>"
        "</div>"
    )


# The shapes really seen in the wild: a dated rolling rc (what the stage instance and the pinned
# test image both report), a plain rc, and a final release.
@pytest.mark.parametrize("reported", ["v4.0.0-rc-260818", "v4.0.0-rc", "v4.0.0", "4.0.0", "v4.1.2"])
def test_supported_versions_are_accepted(reported):
    sm = SchemaManager(_about(reported))
    assert sm.major == SUPPORTED_ELN_MAJOR


def test_dated_release_candidate_parses_to_its_numeric_version():
    sm = SchemaManager(_about("v4.0.0-rc-260818"))
    assert (sm.major, sm.minor, sm.patch) == (4, 0, 0)
    assert sm.version == "4.0.0"


def test_older_major_is_rejected_and_the_error_names_both_versions():
    with pytest.raises(UnsupportedServerVersion) as excinfo:
        SchemaManager(_about("v3.1.2"))
    message = str(excinfo.value)
    assert "3.1.2" in message, "the error should say what the server actually runs"
    assert "v4" in message, "the error should say what this client requires"
    assert "312" in message, "the error should point ELN 3.x users at the release line that works"


def test_unparseable_version_raises_instead_of_degrading_silently():
    # This used to fall back to the literal string 'TEST', which then appeared in every built-in
    # element's @type IRI with no error anywhere.
    with pytest.raises(UnsupportedServerVersion):
        SchemaManager(_FakeResponse("<html><body>404 Not Found</body></html>", status_code=404))


def test_version_check_can_be_bypassed_for_deliberate_inspection():
    sm = SchemaManager(_about("v3.1.2"), check_version=False)
    assert sm.version == "3.1.2"


def test_model_type_iri_uses_major_minor_so_it_survives_rebuilds():
    # Two rolling rebuilds of the same minor release must produce the same semantic type.
    first = SchemaManager(_about("v4.0.0-rc-260818"))
    second = SchemaManager(_about("v4.0.0-rc-260901"))
    assert first.generate_model_type("Sample", None) == "chemotion:type/sample/4.0"
    assert first.generate_model_type("Sample", None) == second.generate_model_type("Sample", None)


def test_generic_classes_keep_their_own_schema_version():
    sm = SchemaManager(_about("v4.0.0-rc-260818"))
    assert sm.generate_model_type("try", "1.0") == "chemotion:generic_type/try/1.0"
