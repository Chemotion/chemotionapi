"""The server's native collection export and import, round-tripped against a live ELN v4.

Export is a background job announced by a notification; import runs before the server answers.
"""
import zipfile

from chemotion_api.collection import Collection


def test_export_then_import_round_trip(instance_with_collection: dict, tmp_path):
    instance = instance_with_collection['instance']
    col: Collection = instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.properties['description'] = 'round trip'
    sample.save()

    archive = col.export_zip(tmp_path / 'export.zip', timeout=300)
    assert zipfile.is_zipfile(archive)
    with zipfile.ZipFile(archive) as z:
        assert 'export.json' in z.namelist()

    imported = instance.import_zip(archive)
    assert [c.label for c in imported] == [col.label]
    copies = list(imported[0].get_samples())
    assert len(copies) == 1
    assert copies[0].id != sample.id
    assert 'round trip' in str(copies[0].properties['description'])
