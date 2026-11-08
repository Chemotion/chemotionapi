"""Structure search: substructure and similarity, over every element type (M2.4).

``POST /api/v1/search/structure``, the UI's structure search. The server matches the query
structure against sample fingerprints and returns the matching samples together with the elements
associated with them (reactions, wellplates, screens, research plans, generic elements).
"""
from __future__ import annotations

from typing import Self

from chemotion_api.connection import Connection
from chemotion_api.element_manager import ElementManager
from chemotion_api.elements import ElementSet
from chemotion_api.elements.registry import element_type_info
from chemotion_api.elements.sample import Molecule, MoleculeManager

SUBSTRUCTURE = 'sub'
SIMILAR = 'similar'


class StructureSearchResult:
    """The result of a structure search: one :class:`~chemotion_api.elements.ElementSet` per type.

    Each set holds at most the searcher's :meth:`~StructureSearcher.find_max` elements, loaded
    partially (like any list) and loading in full on first access; :meth:`total` is the number of
    matches on the server.
    """

    def __init__(self, sets: dict[str, ElementSet], totals: dict[str, int]):
        self._sets = sets
        self._totals = totals

    def __getitem__(self, element_type: str) -> ElementSet:
        """The found elements of a type, by element type name: ``'sample'``, ``'reaction'``, or a
        generic element type's name.

        :raises KeyError: for a type this client has no class for; its matches
            are still counted in :meth:`total`.
        """
        return self._sets[element_type]

    @property
    def types(self) -> list[str]:
        """The element types with at least one match."""
        return [t for t, total in self._totals.items() if total]

    def total(self, element_type: str) -> int:
        """How many elements of ``element_type`` match, including those beyond :meth:`find_max`."""
        return self._totals.get(element_type, 0)

    samples = property(lambda self: self._sets['sample'])
    reactions = property(lambda self: self._sets['reaction'])
    wellplates = property(lambda self: self._sets['wellplate'])
    screens = property(lambda self: self._sets['screen'])
    research_plans = property(lambda self: self._sets['research_plan'])


class StructureSearcher:
    """
    Builds and runs a structure search. Pick the kind with :meth:`substructure` or :meth:`similar`,
    optionally narrow it with :meth:`in_collection` and :meth:`find_max`, then :meth:`request`.

    >>> result = instance.search_structure().substructure('c1ccccc1O').find_max(50).request()
    >>> for sample in result.samples: ...
    >>> result.total('reaction')
    """

    def __init__(self, connection: Connection, element_manager: ElementManager, root_collection_id: int):
        self._connection = connection
        self._element_manager = element_manager
        self._collection_id = root_collection_id
        self._per_page = 15
        self._search_type: str | None = None
        self._threshold = 0.7
        self._structure: str | Molecule | None = None

    def substructure(self, structure: str | Molecule) -> Self:
        """Find elements whose structure contains ``structure``.

        :param structure: SMILES, a molfile, or a :class:`~chemotion_api.elements.sample.Molecule`.
        """
        self._search_type, self._structure = SUBSTRUCTURE, structure
        return self

    def similar(self, structure: str | Molecule, threshold: float = 0.7) -> Self:
        """Find elements whose structure is similar to ``structure``.

        :param structure: SMILES, a molfile, or a :class:`~chemotion_api.elements.sample.Molecule`.
        :param threshold: minimum Tanimoto similarity of the fingerprints, from 0 to 1.
        """
        if not 0 <= threshold <= 1:
            raise ValueError('The Tanimoto threshold is between 0 and 1.')
        self._search_type, self._structure, self._threshold = SIMILAR, structure, threshold
        return self

    def in_collection(self, collection_id: int) -> Self:
        """Search only one collection. By default the 'All' collection is searched."""
        self._collection_id = collection_id
        return self

    def find_max(self, per_page: int) -> Self:
        """The most elements to return per type (default 15)."""
        if per_page < 1:
            raise ValueError('find_max needs at least 1.')
        self._per_page = per_page
        return self

    def _molfile(self) -> str:
        structure = self._structure
        if isinstance(structure, Molecule):
            molfile = structure['molfile']
            if not molfile:
                raise ValueError('The molecule has no molfile.')
            return molfile
        if not structure or not str(structure).strip():
            raise ValueError('No structure given.')
        if 'M  END' in structure or '\n' in structure:
            return structure
        # SMILES: the server searches by molfile. Resolving it registers the molecule on the server,
        # as drawing it in the UI's editor would.
        return MoleculeManager(self._connection).create_molecule_by_smiles(structure)['molfile']

    def payload(self) -> dict:
        """The request body :meth:`request` sends."""
        if self._search_type is None:
            raise ValueError('Choose substructure() or similar() first.')
        return {
            'selection': {
                'elementType': 'structure',
                'search_by_method': 'structure',
                'structure_search': True,
                'molfile': self._molfile(),
                'search_type': self._search_type,
                'tanimoto_threshold': self._threshold,
                'page_size': self._per_page,
            },
            'collection_id': str(self._collection_id),
            'page': 1,
            'per_page': self._per_page,
            'molecule_sort': True,
            'is_public': False,
        }

    def request(self) -> StructureSearchResult:
        """Runs the search.

        :raises ValueError: if no search kind or structure was set.
        :raises ConnectionError: if the search request fails.
        """
        res = self._connection.post('/api/v1/search/structure', data=self.payload())
        if res.status_code not in (200, 201):
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        data = res.json() or {}
        sets: dict[str, ElementSet] = {}
        totals: dict[str, int] = {}
        for name, klass in self._element_manager.all_classes.items():
            block = data.get(f'{name}s')
            if not isinstance(block, dict) or name == 'generic_element':
                continue
            totals[name] = int(block.get('totalElements') or 0)
            if not klass.get('is_generic') and element_type_info(name) is None:
                continue  # a type this client has no class for: counted only
            element_set = ElementSet(self._connection, klass, self._collection_id, fixed_length=True)
            for row in block.get('elements') or []:
                element_set.new_element(row).mark_partial()
            sets[name] = element_set
        return StructureSearchResult(sets, totals)
