"""Safety data sheets and inventory labels on a live ELN (M4.5)."""
import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def sample(instance_with_collection):
    s = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    s.save()
    return s


def test_manual_safety_sheet(instance_with_collection, sample, tmp_path):
    instance = instance_with_collection['instance']
    pdf = tmp_path / 'sds.pdf'
    pdf.write_bytes(b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n')
    chemical = sample.attach_safety_sheet(str(pdf), 'Merck', 'merckProductInfo', {'productNumber': 'E7023'},
                                          cas='64-17-5')
    (path,) = chemical.safety_sheets
    assert path.startswith('/safety_sheets/Merck/') and chemical.data['merckProductInfo']['productNumber'] == 'E7023'
    assert open(instance.download_safety_sheet(path, str(tmp_path / 'back.pdf')), 'rb').read().startswith(b'%PDF')
    with pytest.raises(ValueError, match='Cannot read'):  # a sheet without text
        instance.extract_safety_sheet(path)


def test_inventory_label(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    assert col.inventory_label() is None
    prefix = f'T{uuid.uuid4().hex[:4].upper()}'
    instance.set_inventory_label(prefix, 'API test inventory', 0, col)
    label = col.inventory_label()
    assert (label.prefix, label.name, label.counter) == (prefix, 'API test inventory', 0)
    grouped = [g for g in instance.inventory_collections() if (g.get('inventory') or {}).get('prefix') == prefix]
    assert [c['id'] for c in grouped[0]['collections']] == [col.id]
