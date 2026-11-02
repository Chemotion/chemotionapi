"""Creating a molecule from SMILES — two fixes ported from version-3 (PR #6).

Both are pure client logic against `POST /api/v1/molecules/smiles`, which still exists unchanged
at v4.0.0, so they port from a 3.1.2-targeted branch without rework.
"""
import json

import pytest

from chemotion_api.elements.sample import MoleculeManager


class _Res:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res):
        self._res, self.calls = res, []

    def post(self, url, data=None, **kwargs):
        self.calls.append((url, data))
        return self._res


def _manager(res):
    mgr = MoleculeManager.__new__(MoleculeManager)
    mgr._session = _Session(res)
    return mgr


@pytest.mark.parametrize("payload", [{}, {"id": None}, None])
def test_an_unresolvable_smiles_fails_here_not_500_later(payload):
    """The server answers 201 with an *empty* molecule rather than an error. Building a sample on
    that fails with a 500 far from the cause, so the guard has to be client-side."""
    with pytest.raises(ValueError, match=r"\[Mg\]"):
        _manager(_Res(201, payload)).create_molecule_by_smiles("Mg")


def test_omitting_density_keeps_what_the_server_stored():
    """The old default was 0.0 and it was written back unconditionally, so every caller that did
    not pass a density silently replaced the real one with zero."""
    mol = _manager(_Res(201, {"id": 7, "density": 0.789})).create_molecule_by_smiles("CCO")
    assert mol["density"] == 0.789


def test_an_explicit_density_still_wins():
    mol = _manager(_Res(201, {"id": 7, "density": 0.789})).create_molecule_by_smiles("CCO", 1.5)
    assert mol["density"] == 1.5


def test_a_non_201_is_a_connection_error():
    with pytest.raises(ConnectionError):
        _manager(_Res(500, {})).create_molecule_by_smiles("CCO")


# ------------------------------------------------------- attribute access (ported, adapted)

def _molecule(data):
    from chemotion_api.elements.sample import Molecule
    return Molecule(data)


def test_a_known_field_is_reachable_as_an_attribute():
    """`molecule.molecular_weight` rather than `molecule['molecular_weight']`."""
    mol = _molecule({"id": 1, "molecular_weight": 46.07})
    assert mol.molecular_weight == 46.07
    assert mol["molecular_weight"] == 46.07       # bracket access still works


def test_an_extra_field_the_server_sent_is_reachable_too():
    mol = _molecule({"id": 1, "something_new": "x"})
    assert mol.something_new == "x"


def test_an_unknown_name_raises_attribute_error_not_key_error():
    mol = _molecule({"id": 1})
    with pytest.raises(AttributeError, match="no attribute or key"):
        _ = mol.definitely_not_a_field


def test_private_names_are_never_answered_from_the_payload():
    """__getattr__ must not resolve `_model` from the data: during __init__ it does not exist
    yet, and answering here would recurse until the stack dies."""
    mol = _molecule({"id": 1, "_model": "hostile", "__class__": "hostile"})
    assert not isinstance(mol._model, str)        # the real model, not the payload's value
    with pytest.raises(AttributeError):
        _ = mol._not_a_real_attribute


def test_real_methods_are_not_shadowed_by_payload_keys():
    mol = _molecule({"id": 1, "clean": "not a method"})
    assert callable(mol.clean)
