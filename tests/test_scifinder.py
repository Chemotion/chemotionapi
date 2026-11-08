"""SciFinder-n on a live ELN (M7.7). The seeded accounts hold no SciFinder-n credential."""
import pytest

pytestmark = pytest.mark.integration


def test_without_a_credential(logged_in_instance):
    assert logged_in_instance.scifinder_credential() is None
    molfile = logged_in_instance.molecule().create_molecule_by_smiles('CCO')['molfile']
    with pytest.raises(PermissionError, match='token'):
        logged_in_instance.scifinder_search(molfile)
