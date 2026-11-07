"""Components of mixture samples (``/api/v1/components``, M2.3)."""
from __future__ import annotations

from typing import Any

from chemotion_api.connection import Connection, request_error

#: ``component_properties`` keys the server accepts (``component_api.rb``).
PROPERTY_KEYS = (
    'amount_mol', 'amount_l', 'amount_g', 'relative_molecular_weight', 'density', 'molarity_unit',
    'molarity_value', 'starting_molarity_value', 'starting_molarity_unit', 'molecule_id', 'equivalent',
    'parent_id', 'material_group', 'reference', 'purity',
)


class Component:
    """One component of a mixture sample: a molecule plus its amounts.

    ``properties`` holds the server's ``component_properties`` — ``amount_mol`` (mol),
    ``amount_g`` (g), ``amount_l`` (l), ``density`` (g/ml), ``molarity_value``/``_unit``,
    ``purity``, ``equivalent``, ``reference`` (the component ratios are relative to),
    ``material_group`` (``'liquid'`` or ``'solid'``), … — except the molecule, which is
    :attr:`molecule`.
    """

    def __init__(self, data: dict[str, Any]):
        from chemotion_api.elements.sample import Molecule  # sample imports this module
        data = dict(data)
        props = dict(data.get('component_properties') or {})
        molecule = props.pop('molecule', None)
        self.id: int | str | None = data.get('id')
        self.name: str | None = data.get('name')
        self.position: int | None = data.get('position')
        self.sample_id: int | None = data.get('sample_id')
        self.properties: dict[str, Any] = props
        self.molecule = Molecule(molecule) if molecule else None

    def __repr__(self) -> str:
        return f'Component(id={self.id!r}, name={self.name!r})'

    @classmethod
    def new(cls, molecule, name: str | None = None, **properties) -> Component:
        """A new component of ``molecule``, to pass to :meth:`Sample.save_components`.

        :param molecule: a :class:`~chemotion_api.elements.sample.Molecule` (e.g. from
            ``instance.molecule().create_molecule_by_smiles(...)``).
        :param name: defaults to the molecule's IUPAC name, as in the UI.
        :param properties: any of :data:`PROPERTY_KEYS`, e.g. ``amount_mol=0.01, material_group='liquid'``.
        """
        unknown = set(properties) - set(PROPERTY_KEYS)
        if unknown:
            raise ValueError(f'Unknown component properties: {", ".join(sorted(unknown))}')
        component = cls({'id': None, 'name': name, 'component_properties': properties})
        component.molecule = molecule
        return component

    @property
    def molecule_id(self) -> int | None:
        if self.molecule is not None and self.molecule.id is not None:
            return self.molecule.id
        return self.properties.get('molecule_id')

    def to_payload(self, new_id: str, position: int) -> dict[str, Any]:
        molecule_id = self.molecule_id
        if molecule_id is None:
            raise ValueError(f'{self!r} has no molecule.')
        props = {k: v for k, v in self.properties.items() if k in PROPERTY_KEYS and v is not None}
        props['molecule_id'] = molecule_id
        name = self.name
        if name is None and self.molecule is not None:
            name = self.molecule['iupac_name'] or self.molecule['cano_smiles']
        return {'id': self.id if self.id is not None else new_id, 'name': name or '',
                'position': self.position if self.position is not None else position,
                'component_properties': props}


def load_components(session: Connection, sample_id: int) -> list[Component]:
    res = session.get(f'/api/v1/components/{sample_id}')
    if res.status_code != 200:
        raise request_error(res, f'loading the components of sample {sample_id}')
    return sorted((Component(c) for c in res.json() or []), key=lambda c: (c.position is None, c.position))


def save_components(session: Connection, sample_id: int, components: list[Component]) -> list[Component]:
    payload = [c.to_payload(f'new_{n}', n) for n, c in enumerate(components, start=1)]
    res = session.put('/api/v1/components', data={'sample_id': sample_id, 'components': payload})
    if res.status_code != 200:
        raise request_error(res, f'saving the components of sample {sample_id}')
    return sorted((Component(c) for c in res.json() or []), key=lambda c: (c.position is None, c.position))
