"""Sequence-based macromolecules (SBMM) and their samples (M4.4).

A *sequence-based macromolecule* is a protein record — sequence, names, UniProt link, modifications
— shared by every sample of it. A *SBMM sample* (``SbmmSample``) is the element: one batch of the
macromolecule with its amounts, concentration and activity. Saving a sample saves its macromolecule
along with it (``sequence_based_macromolecule_attributes``); a macromolecule already used by other
people's samples cannot be changed that way and asks for a change request instead.
``/api/v1/sequence_based_macromolecule_samples``, ``/api/v1/sequence_based_macromolecules``.
"""
from __future__ import annotations

import copy
from typing import Any, cast

from chemotion_api.connection import Connection, request_error
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.registry import register_element_type

#: The sample's own fields (``sbmm_sample_params``); amounts come as ``*_value`` / ``*_unit`` pairs.
SAMPLE_FIELDS = (
    'name', 'external_label', 'function_or_application', 'inventory_sample',
    'concentration_value', 'concentration_unit', 'concentration_rt_value', 'concentration_rt_unit',
    'molarity_value', 'molarity_unit', 'activity_per_volume_value', 'activity_per_volume_unit',
    'activity_per_mass_value', 'activity_per_mass_unit', 'volume_as_used_value', 'volume_as_used_unit',
    'amount_as_used_mol_value', 'amount_as_used_mol_unit', 'amount_as_used_mass_value', 'amount_as_used_mass_unit',
    'activity_value', 'activity_unit', 'obtained_by', 'supplier', 'formulation', 'purity', 'purity_detection',
    'purification_method', 'heterologous_expression', 'organism', 'taxon_id', 'strain', 'tissue', 'localisation',
)
#: The macromolecule fields the server accepts (``sbmm_params``).
SBMM_FIELDS = (
    'sbmm_type', 'sbmm_subtype', 'uniprot_derivation', 'other_identifier', 'primary_accession', 'parent_identifier',
    'own_identifier', 'ec_numbers', 'full_name', 'short_name', 'molecular_weight', 'sequence', 'link_pdb', 'pdb_doi',
    'protein_source_details_comments', 'protein_source_details_expression_system',
)
#: Entity key -> param key of the two modification records.
_MODIFICATIONS = {'protein_sequence_modifications': 'protein_sequence_modification_attributes',
                  'post_translational_modifications': 'post_translational_modification_attributes'}
#: ``uniprot_derivation`` values: taken from UniProt as is, derived from a UniProt or ELN entry, or unknown there.
UNIPROT_DERIVATIONS = ('uniprot', 'uniprot_modified', 'uniprot_unknown')


class SbmmUpdateNotAllowed(PermissionError):
    """The macromolecule is used elsewhere and cannot be changed through this sample; file a
    change request (:func:`request_change`) instead. ``original`` and ``requested`` are the server's
    two versions."""

    def __init__(self, message: str, original: dict | None = None, requested: dict | None = None):
        super().__init__(message)
        self.original, self.requested = original or {}, requested or {}


@register_element_type('sequence_based_macromolecule_sample', url='/api/v1/sequence_based_macromolecule_samples')
class SbmmSample(AbstractElement):
    """
    A sample of a sequence-based macromolecule. It extends
    :class:`chemotion_api.elements.abstract_element.AbstractElement`.

    ``properties`` holds :data:`SAMPLE_FIELDS` and, under ``'sequence_based_macromolecule'``, the
    macromolecule as a dict (:data:`SBMM_FIELDS` plus the read-only ``id``, ``sequence_length``, …,
    and the ``protein_sequence_modifications`` / ``post_translational_modifications`` records).

    Usage::

    >>> s = collection.new_sbmm_sample()
    >>> s.properties['name'] = 'Lysozyme batch 1'
    >>> s.properties['sequence_based_macromolecule'].update(
    ...     uniprot_derivation='uniprot_unknown', short_name='LYZ', sequence='KVFGRCELAAAMKRH...')
    >>> s.save()
    >>> # or from UniProt:
    >>> s.use_uniprot('P61626')
    """

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        props: dict[str, Any] = {key: data.get(key) for key in SAMPLE_FIELDS}
        sbmm = copy.deepcopy(data.get('sequence_based_macromolecule') or {})
        sbmm.setdefault('sbmm_type', 'protein')
        sbmm.setdefault('sbmm_subtype', 'unmodified')
        for key in _MODIFICATIONS:
            sbmm.setdefault(key, {})
        props['sequence_based_macromolecule'] = sbmm
        return props

    @property
    def macromolecule(self) -> dict:
        """The macromolecule (``properties['sequence_based_macromolecule']``)."""
        return self.properties['sequence_based_macromolecule']

    def use_uniprot(self, accession: str) -> SbmmSample:
        """Make this sample's macromolecule the UniProt entry ``accession``, as the editor's
        UniProt search does (``uniprot_derivation='uniprot'``). Sent on :meth:`save`."""
        entry = load_macromolecule(self._session, accession, source='uniprot')
        sbmm = dict(entry, uniprot_derivation='uniprot', primary_accession=accession)
        sbmm['sbmm_type'] = sbmm.get('sbmm_type') or 'protein'
        sbmm['sbmm_subtype'] = sbmm.get('sbmm_subtype') or 'unmodified'
        self.properties['sequence_based_macromolecule'] = sbmm
        return self

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        out: dict[str, Any] = {k: self.properties.get(k) for k in SAMPLE_FIELDS if self.properties.get(k) is not None}
        attrs = macromolecule_attributes(self.macromolecule)
        out['sequence_based_macromolecule_attributes'] = attrs
        if cast(dict, self.json_data).get('collection_id') is not None:
            out['collection_id'] = cast(dict, self.json_data)['collection_id']
        return out

    def clean_data(self) -> dict:
        sbmm = self.macromolecule
        derivation = sbmm.get('uniprot_derivation')
        if derivation not in UNIPROT_DERIVATIONS:
            raise ValueError(f'Set the macromolecule\'s uniprot_derivation to one of {", ".join(UNIPROT_DERIVATIONS)}.')
        if derivation == 'uniprot' and not sbmm.get('primary_accession'):
            raise ValueError('A UniProt macromolecule needs its primary_accession.')
        if derivation != 'uniprot' and not (sbmm.get('short_name') and sbmm.get('sequence')):
            raise ValueError('A macromolecule not taken from UniProt needs a short_name and a sequence.')
        data = super().clean_data()
        data.pop('sequence_based_macromolecule', None)
        return data

    def save(self, load_after_save: bool = False):
        try:
            return super().save(load_after_save)
        except Exception as e:  # turn the server's conflict answer into something actionable
            response = getattr(e, 'response', None)
            body = _json_or_none(response)
            error = (body or {}).get('error') if isinstance(body, dict) else None
            if isinstance(error, dict) and error.get('type') == 'SbmmUpdateNotAllowed':
                raise SbmmUpdateNotAllowed(error.get('message', 'The macromolecule cannot be changed here.'),
                                           error.get('original_sbmm'), error.get('requested_changes')) from e
            if isinstance(error, dict) and error.get('type') == 'ForbiddenUniprotDerivationChange':
                raise ValueError(error.get('message')) from e
            raise


def macromolecule_attributes(sbmm: dict) -> dict:
    """A macromolecule dict as the server's ``sbmm_params`` take it."""
    attrs: dict[str, Any] = {k: sbmm.get(k) for k in SBMM_FIELDS if sbmm.get(k) is not None}
    if sbmm.get('uniprot_derivation') == 'uniprot_modified' and not attrs.get('parent_identifier'):
        parent = sbmm.get('parent') or {}
        if parent:
            attrs['parent_identifier'] = str(parent.get('id') or parent.get('primary_accession'))
    if sbmm.get('uniprot_derivation') != 'uniprot':
        for entity_key, param_key in _MODIFICATIONS.items():
            attrs[param_key] = {k: v for k, v in (sbmm.get(entity_key) or {}).items()
                                if k not in ('id', 'created_at', 'updated_at', 'deleted_at') and v is not None}
    return attrs


def _json_or_none(response) -> Any:
    try:
        return response.json() if response is not None else None
    except ValueError:
        return None


def search_macromolecules(session: Connection, term: str, field: str = 'accession') -> list[dict]:
    """Search this ELN's macromolecules and UniProt, as the editor's search does
    (``GET /api/v1/sequence_based_macromolecules``). Each result says in ``available_sources``
    whether it is in the ELN (``id`` set) or only in UniProt (``primary_accession``).

    :param field: ``'accession'``, ``'ec'``, ``'protein_name'`` or ``'sequence'``.
    """
    if field not in ('accession', 'ec', 'protein_name', 'sequence'):
        raise ValueError("field is 'accession', 'ec', 'protein_name' or 'sequence'.")
    res = session.get('/api/v1/sequence_based_macromolecules', params={'search_field': field, 'search_term': term})
    if res.status_code != 200:
        raise request_error(res, f'searching macromolecules for "{term}"')
    return res.json().get('search_results') or []


def load_macromolecule(session: Connection, identifier: int | str, source: str = 'eln') -> dict:
    """One macromolecule: an ELN record by id (``source='eln'``) or a UniProt entry by accession
    (``source='uniprot'``)."""
    if source not in ('eln', 'uniprot'):
        raise ValueError("source is 'eln' or 'uniprot'.")
    res = session.get(f'/api/v1/sequence_based_macromolecules/{identifier}', params={'type': source})
    if res.status_code != 200:
        raise request_error(res, f'loading macromolecule {identifier} from {source}')
    return res.json().get('sequence_based_macromolecule') or {}


def request_change(session: Connection, macromolecule: dict) -> None:
    """Ask this ELN's administrators to change a macromolecule you may not change yourself
    (``POST /api/v1/sequence_based_macromolecules/change_request``); they get an email.

    :param macromolecule: the macromolecule as you want it (as in ``SbmmSample.macromolecule``).
    """
    res = session.post('/api/v1/sequence_based_macromolecules/change_request',
                       data=macromolecule_attributes(macromolecule))
    if res.status_code not in (200, 201, 204):
        raise request_error(res, 'requesting a macromolecule change')
