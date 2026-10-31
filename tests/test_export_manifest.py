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


def _mock_collection_with_failing_download():
    """A collection whose one sample loads/maps fine but whose only attachment fails to download
    -- the "download" skip stage only ever gets appended while the crate ZIP is being written."""
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
    sample.to_dcat_ap.side_effect = Exception("mapping boom")
    sample.eln_node_content.return_value = {}
    del sample.analyses

    broken_att = MagicMock()
    att_dict = {"filename": "broken.txt", "filesize": 5, "mime_type": "text/plain"}
    broken_att.get.side_effect = lambda k, default=None: att_dict.get(k, default)
    broken_att.__getitem__.side_effect = lambda k: att_dict[k]
    broken_att.iter_file.side_effect = Exception("download broke")
    sample.attachments = [broken_att]

    col.get_samples.return_value = [sample]
    col.get_reactions.return_value = []
    col.get_wellplates.return_value = []
    col.get_research_plans.return_value = []
    col.get_generics_by_name.return_value = []
    return col


def test_strict_export_raises_on_download_failure_and_leaves_no_file(tmp_path):
    """Regression test for PR review finding 7: an attachment-download failure discovered only
    while the crate ZIP is being written must still fail strict mode *before* any file is left
    behind at the destination path -- no complete crate, and no leftover ``.part`` temp file."""
    col = _mock_collection_with_failing_download()
    out = tmp_path / "strict_download.eln"

    with pytest.raises(RuntimeError, match="strict mode"):
        Collection.export_eln(col, str(out), strict=True, authors=_authors())

    assert not out.exists(), "strict mode must not leave a (partial or complete) crate behind"
    assert not (tmp_path / "strict_download.eln.part").exists(), "temp file must be cleaned up"
    # sanity: the same setup in non-strict mode does produce a crate (download failure is
    # recorded in the manifest, not fatal)
    out2 = tmp_path / "lenient_download.eln"
    result = Collection.export_eln(col, str(out2), authors=_authors())
    assert result == str(out2)
    assert out2.exists()
