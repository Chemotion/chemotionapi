"""Collection export and import on a live ELN (M3.1). Needs the stack's background worker."""
import zipfile

import pytest

pytestmark = pytest.mark.integration


def test_export_and_import_round_trip(instance_with_collection, tmp_path):
    col = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.properties['name'] = 'exported ethanol'
    sample.save()

    archive = col.export(str(tmp_path / 'export.zip'), timeout=180)
    with zipfile.ZipFile(archive) as z:
        assert 'export.json' in z.namelist()

    root = instance_with_collection['instance'].get_root_collection()
    imported = root.import_collections(archive, timeout=180)
    assert [c.label for c in imported] == [col.label]
    assert imported[0].id != col.id
    names = [s.properties['name'] for s in imported[0].get_samples(per_page=None)]
    assert names == ['exported ethanol']


def test_exporting_someone_elses_collection_is_refused(instance_with_collection, tmp_path):
    col = instance_with_collection['main_collection']
    real_id = col.id
    col._id = 1_000_000_000
    try:
        with pytest.raises((PermissionError, ConnectionError)):
            col.export(str(tmp_path / 'x.zip'), timeout=5)
    finally:
        col._id = real_id
