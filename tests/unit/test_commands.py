"""Offline tests for the instance-management CLI helpers.

Covers the items raised in review of PR #1: that the Docker Hub version helpers work and time out,
and that `insert_dataset` cannot be broken (or injected into) by the text an ontology API returns.
"""
from unittest.mock import MagicMock, patch

from chemotion_api.commands import InstanceManager

# One page of the Docker Hub tag listing, trimmed to the shapes the helpers care about: `eln-`
# tags are the ELN versions, everything else (db-, spectra-, latest) must be ignored.
_HUB_TAGS = {
    "results": [
        {"name": "eln-3.1.2"},
        {"name": "eln-2.1.1"},
        {"name": "db-3.1.2"},
        {"name": "spectra-1.3.2"},
        {"name": "latest"},
    ]
}


def _hub_response(payload=None):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload if payload is not None else _HUB_TAGS
    return response


def test_get_versions_returns_only_eln_tags_without_the_prefix():
    with patch("chemotion_api.commands.requests.get", return_value=_hub_response()) as get:
        assert InstanceManager.get_versions() == ["3.1.2", "2.1.1"]
    # A hung registry must not hang the CLI forever.
    assert get.call_args.kwargs.get("timeout"), "the Docker Hub request needs a timeout"


def test_get_versions_ignores_non_eln_tags():
    payload = {"results": [{"name": "db-3.1.2"}, {"name": "latest"}]}
    with patch("chemotion_api.commands.requests.get", return_value=_hub_response(payload)):
        assert InstanceManager.get_versions() == []


def test_get_image_of_versions_resolves_a_known_version():
    with patch("chemotion_api.commands.requests.get", return_value=_hub_response()):
        images = InstanceManager.get_image_of_versions("3.1.2")
    assert isinstance(images, dict) and images, "expected a mapping of service -> image tag"
    # Whatever the exact keys, the resolved version must appear in the image references.
    assert any("3.1.2" in str(v) for v in images.values())


def test_get_image_of_versions_returns_nothing_for_an_unknown_version():
    """Documents a sharp edge rather than endorsing it.

    An unrecognised version yields an empty mapping instead of an error, so `update(version=...)`
    with a typo'd version quietly updates nothing. Left as-is here because changing it is a
    behaviour change beyond the review's scope — but it is worth a clear failure one day.
    """
    with patch("chemotion_api.commands.requests.get", return_value=_hub_response()):
        assert InstanceManager.get_image_of_versions("0.0.0-nope") == {}


def test_insert_dataset_passes_ontology_text_as_psql_variables_not_inline_sql():
    """A definition containing a quote must not be able to break (or extend) the statement.

    The values come from EBI OLS, i.e. from outside this codebase, so they are passed with psql's
    -v/:'name' quoting rather than interpolated into the SQL text.
    """
    hostile_label = "Bob's spectroscopy"
    hostile_definition = "ends with '); DROP TABLE dataset_klasses; --"
    ols = MagicMock()
    ols.status_code = 200
    ols.json.return_value = {
        "curie": "CHMO:0000595",
        "label": hostile_label,
        "definition": {"value": hostile_definition},
    }

    with patch("chemotion_api.commands.requests.get", return_value=ols), \
            patch("chemotion_api.commands.subprocess.Popen") as popen:
        popen.return_value.communicate.return_value = (b"", b"")
        InstanceManager.insert_dataset("CHMO:0000595")

    command = popen.call_args.args[0]
    sql = command[command.index("-c") + 1]

    # The dangerous text must not appear in the statement at all...
    assert hostile_definition not in sql
    assert hostile_label not in sql
    assert "DROP TABLE" not in sql
    # ...it must arrive as psql variables, referenced through the quoting form :'name'.
    assert f"label={hostile_label}" in command
    assert f"definition={hostile_definition}" in command
    assert ":'label'" in sql and ":'definition'" in sql
