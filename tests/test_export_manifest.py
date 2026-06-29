"""Offline test for export observability: skipped-manifest warning + strict mode (#1).

Heavy: both tests run a full export_eln (rdflib JSON-LD serialization), so they're marked `heavy`.
"""
from unittest.mock import MagicMock

import pytest

from chemotion_api import Author, AuthorAffiliation
from chemotion_api.collection import Collection

pytestmark = pytest.mark.heavy


def _authors():
    return [Author(name="Test Author", orcid="0000-0002-1825-0097",
                   affiliations=[AuthorAffiliation(name="Org", ror="https://ror.org/04t3en479")])]


def _mock_collection_with_failing_sample():
    root_col = MagicMock()
    root_col._element_manager.all_classes = {"sample": {"label": "Sample"}}
    col = MagicMock()
    col.id = 1
    col.label = "Manifest Col"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    col.children = []

    sample = MagicMock()
    sample.id = 1001
    sample.name = "S"
    sample._data_loaded = True
    sample.properties = {"short_label": "S-1001"}
    sample.attachments = []
    sample.to_dcat_ap.side_effect = Exception("mapping boom")  # -> recorded in manifest
    sample.eln_node_content.return_value = {}  # real dict, not a Mock (Mock would break json serialization)
    del sample.analyses

    col.get_samples.return_value = [sample]
    col.get_reactions.return_value = []
    col.get_wellplates.return_value = []
    col.get_research_plans.return_value = []
    col.get_generics_by_name.return_value = []
    return col


def test_strict_export_raises_on_issue(tmp_path):
    col = _mock_collection_with_failing_sample()
    with pytest.raises(RuntimeError, match="strict mode"):
        Collection.export_eln(col, str(tmp_path / "strict.eln"), strict=True, authors=_authors())


def test_nonstrict_export_proceeds_despite_issue(tmp_path):
    col = _mock_collection_with_failing_sample()
    out = tmp_path / "lenient.eln"
    result = Collection.export_eln(col, str(out), authors=_authors())  # default strict=False
    assert result == str(out)
    assert out.exists()  # export still produced a crate
