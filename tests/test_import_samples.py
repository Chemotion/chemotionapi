"""Sample import on a live ELN (M2.5). Needs the stack's background worker (CONFIG_ROLE=combine)."""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def sdf_file(logged_in_instance, tmp_path):
    mm = logged_in_instance.molecule()
    path = tmp_path / 'three.sdf'
    path.write_text(''.join(mm.create_molecule_by_smiles(s)['molfile'] + '\n$$$$\n'
                            for s in ('CCO', 'CCCO', 'CC(=O)O')))
    return str(path)


def test_import_an_sdf_and_wait(instance_with_collection, sdf_file):
    col = instance_with_collection['main_collection']
    result = col.import_samples(sdf_file, timeout=180)
    assert result.ok, result.message
    smiles = {s.molecule['cano_smiles'] for s in col.get_samples(per_page=None)}
    assert smiles == {'CCO', 'CCCO', 'CC(=O)O'}


def test_import_as_chemicals(instance_with_collection, sdf_file):
    col = instance_with_collection['main_collection']
    assert col.import_samples(sdf_file, as_chemicals=True, timeout=180).ok
    assert all(s.properties.get('inventory_sample') for s in col.get_samples(per_page=None))


def test_a_broken_file_reports_an_error(instance_with_collection, tmp_path):
    path = tmp_path / 'broken.sdf'
    path.write_text('not a structure\n$$$$\n')
    result = instance_with_collection['main_collection'].import_samples(str(path), timeout=180)
    assert result.level == 'error' and not result.ok
