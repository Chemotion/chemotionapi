"""Mixture components on a live ELN (M2.3)."""
import pytest

from chemotion_api.elements.components import Component

pytestmark = pytest.mark.integration


@pytest.fixture()
def mixture(instance_with_collection):
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.properties['sample_type'] = 'Mixture'
    sample.save()
    return sample


def test_set_edit_and_drop_components(logged_in_instance, mixture):
    mm = logged_in_instance.molecule()
    stored = mixture.save_components([
        Component.new(mm.create_molecule_by_smiles('CCO'), amount_mol=0.01, material_group='liquid'),
        Component.new(mm.create_molecule_by_smiles('O'), name='water', amount_mol=0.02, material_group='liquid'),
    ])
    assert [c.molecule['cano_smiles'] for c in stored] == ['CCO', 'O']
    assert stored[1].name == 'water'

    current = mixture.components()
    current[0].properties['amount_mol'] = 0.05
    mixture.save_components(current[:1])

    (only,) = mixture.components()
    assert (only.id, only.properties['amount_mol']) == (stored[0].id, 0.05)


def test_saving_the_sample_keeps_its_components(logged_in_instance, mixture):
    mixture.save_components([Component.new(logged_in_instance.molecule().create_molecule_by_smiles('CCO'),
                                           amount_mol=0.01)])
    reloaded = logged_in_instance.get_sample(mixture.id)
    reloaded.save()
    assert len(mixture.components()) == 1
    assert logged_in_instance.get_sample(mixture.id).is_mixture


def test_a_plain_sample_refuses_components(instance_with_collection):
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCC')
    sample.save()
    with pytest.raises(ValueError, match='Only mixture samples'):
        sample.save_components([])
