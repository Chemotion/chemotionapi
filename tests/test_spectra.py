"""Spectra on a live ELN (M5.1).

The stack has no ChemSpectra service of its own (ELN main points at a public one), so only the
routes that work without one run here: the NMRium link, the regeneration bookkeeping and the LC-MS
page lookup. The rest are unit-tested.
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def text_attachment(instance_with_collection, tmp_path):
    path = tmp_path / 'ir.txt'
    path.write_text('not a spectrum')
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.analyses.add_analyses('IR').add_dataset(str(path))
    sample.save()
    sample.load()
    return sample.analyses.by_name('IR').datasets[0].attachments[0]


def test_routes_that_need_no_spectra_service(logged_in_instance, text_attachment):
    spectra = logged_in_instance.spectra()
    assert spectra.nmrium_url() is None or spectra.nmrium_url().startswith('http')
    spectra.regenerate([text_attachment])  # not a JCAMP root: skipped by the server, no error
    with pytest.raises(LookupError):
        spectra.lcms_page(text_attachment, 1.5)
    with pytest.raises(PermissionError):
        spectra.layouts()  # admins only
