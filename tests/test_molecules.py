"""Molecules on a live ELN (M2.1): molfile input, lookups, names, SVG, molecular weight."""
import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def ethanol(logged_in_instance):
    return logged_in_instance.molecule().create_molecule_by_smiles('CCO')


def test_a_molfile_gives_the_same_molecule_as_its_smiles(logged_in_instance, ethanol):
    mol = logged_in_instance.molecule().create_molecule_by_molfile(ethanol['molfile'])
    assert mol.id == ethanol.id and mol['sum_formular'] == 'C2H6O'


def test_an_unreadable_molfile_raises(logged_in_instance):
    with pytest.raises(ValueError):
        logged_in_instance.molecule().create_molecule_by_molfile('not a molfile')


def test_a_sample_from_a_molfile(instance_with_collection, ethanol):
    sample = instance_with_collection['main_collection'].new_sample_molfile(ethanol['molfile'])
    sample.save()
    assert instance_with_collection['instance'].get_sample(sample.id).molecule.id == ethanol.id


def test_lookup_by_inchikey(logged_in_instance, ethanol):
    mm = logged_in_instance.molecule()
    assert mm.get_molecule_by_inchikey(ethanol['inchikey']).id == ethanol.id
    assert mm.get_molecule_by_inchikey('AAAAAAAAAAAAAA-AAAAAAAAAA-N') is None


def test_names_and_adding_one(logged_in_instance, ethanol):
    mm = logged_in_instance.molecule()
    name = f'API_TEST {uuid.uuid4().hex[:6]}'
    assert name in [n['name'] for n in mm.add_name(ethanol.id, name)]
    assert name in [n['name'] for n in mm.get_names(ethanol.id)]


def test_render_and_load_svg(logged_in_instance, ethanol):
    mm = logged_in_instance.molecule()
    path = mm.render_svg(ethanol['molfile'])
    assert path.startswith('/images/molecules/')
    assert b'<svg' in mm.load_svg(path)


def test_molecular_weight(logged_in_instance):
    assert logged_in_instance.molecule().molecular_weight('C2H6O') == pytest.approx(46.07, abs=0.01)


def test_cas_numbers_come_back_as_a_list(logged_in_instance, ethanol):
    # The server asks PubChem; offline stacks answer an empty list, so only the type is asserted.
    assert isinstance(logged_in_instance.molecule().load_cas(ethanol['inchikey']), list)
