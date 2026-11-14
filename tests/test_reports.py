"""Reports and table exports on a live ELN (M3.2). Report generation needs the background worker."""
import zipfile

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def reaction_setup(instance_with_collection):
    col = instance_with_collection['main_collection']
    start = col.new_sample_smiles('CCCO')
    start.save()
    product = col.new_sample_smiles('CC(=O)O')
    product.save()
    reaction = col.new_reaction()
    reaction.properties['name'] = 'report me'
    reaction.properties['starting_materials'].append(start)
    reaction.properties['products'].append(product)
    reaction.save()
    return instance_with_collection['instance'], col, reaction, start


def test_per_element_files(reaction_setup, tmp_path):
    instance, col, reaction, _ = reaction_setup
    assert zipfile.is_zipfile(reaction.report_docx(str(tmp_path / 'r.docx')))
    assert zipfile.is_zipfile(reaction.export_samples_excel(str(tmp_path / 'r.xlsx')))
    plate = col.new_wellplate()
    plate.save()
    assert zipfile.is_zipfile(plate.export_samples_excel(str(tmp_path / 'w.xlsx')))


def test_table_exports(reaction_setup, tmp_path):
    _, col, reaction, start = reaction_setup
    assert zipfile.is_zipfile(col.export_elements(str(tmp_path / 'e.xlsx'), start, reaction))
    sdf = col.export_elements(str(tmp_path / 'e.sdf'), start, file_format='sdf')
    assert open(sdf).read().count('$$$$') == 1
    smiles = col.export_reaction_smiles(str(tmp_path / 'r.csv'), reaction, notation='SM>>P')
    assert open(smiles).read().strip() == 'CCCO>>CC(=O)O'


def test_generate_download_and_delete_a_report(reaction_setup, tmp_path):
    instance, _, reaction, start = reaction_setup
    assert 'standard' in {t.report_type for t in instance.report_templates()}
    archive = instance.create_report(start, reaction, file_name='api_test_report', timeout=180)
    try:
        assert archive.downloadable
        assert zipfile.is_zipfile(archive.download(str(tmp_path / 'report.docx')))
        assert archive.id in {a.id for a in instance.report_archives()}
    finally:
        archive.delete()
    assert archive.id not in {a.id for a in instance.report_archives()}
