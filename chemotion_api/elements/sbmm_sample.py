"""Sequence-based macromolecule (SBMM) samples — a sample of a protein, typically from UniProt.

The protein itself (the *sequence-based macromolecule*) is a separate record shared by every sample
of it. In this client it is **read-only** (owner, 2026-11-13): chosen by UniProt accession when a
sample is created, then left alone. Editing it through the server can raise conflicts, because the
change would reach every other sample of the same protein.

.. note:: **Limitations.** A new sample's protein can only be chosen by **UniProt accession**;
    proteins that are not in UniProt, or modified variants of one, cannot be created from this
    client — create those in the ELN's web UI. The protein of an existing sample is
    **read-only** here. If either limitation affects your work, please open an issue at
    https://github.com/Chemotion/chemotionapi/issues and describe what you need.
"""
import copy
from typing import Any, cast

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.registry import register_element_type
from chemotion_api.models import SbmmSamplePropertiesModel

#: Scalar sample fields, carried as they are.
SBMM_FIELDS = ('name', 'external_label', 'function_or_application', 'inventory_sample',
               'obtained_by', 'supplier', 'formulation', 'purity', 'purity_detection',
               'purification_method')
#: Value/unit pairs: the server sends `<name>_value` and `<name>_unit`; properties hold
#: `{'value': …, 'unit': …}` like a sample's amounts.
SBMM_QUANTITIES = ('concentration', 'concentration_rt', 'molarity', 'activity_per_volume',
                   'activity_per_mass', 'volume_as_used', 'amount_as_used_mol',
                   'amount_as_used_mass', 'activity')

_IDENTITY_SKIP = {'id', 'created_at', 'updated_at', 'deleted_at', 'sequence_based_macromolecule_id'}


@register_element_type('sequence_based_macromolecule_sample', url='/api/v1/sequence_based_macromolecule_samples')
class SbmmSample(AbstractElement):
    """A sample of a sequence-based macromolecule (a protein).

    ``properties`` holds the sample's own fields; quantities are ``{'value': …, 'unit': …}``.
    :attr:`macromolecule` is the protein, read-only. Samples created in the web UI with a protein
    described by hand load and save as well; their protein is sent back exactly as loaded.

    .. note:: **Limitations.** A new sample's protein can only be chosen by **UniProt accession**;
       proteins that are not in UniProt, or modified variants of one, cannot be created from this
       client — create those in the ELN's web UI. The protein of an existing sample is
       **read-only** here. If either limitation affects your work, please open an issue at
       https://github.com/Chemotion/chemotionapi/issues and describe what you need.

    Usage::

        >>> s = collection.new_sbmm_sample(uniprot='P69905')
        >>> s.properties['purity'] = 0.95
        >>> s.save()
        >>> s.macromolecule['short_name']
        'Hemoglobin subunit alpha'
    """

    _properties_model = SbmmSamplePropertiesModel

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        props: dict[str, Any] = {key: data.get(key) for key in SBMM_FIELDS}
        for q in SBMM_QUANTITIES:
            props[q] = {'value': data.get(f'{q}_value'), 'unit': data.get(f'{q}_unit')}
        return self._validated_properties(props)

    @property
    def macromolecule(self) -> dict:
        """The protein this sample is of, as the server describes it — a copy; read-only."""
        return copy.deepcopy(cast(dict, self.json_data).get('sequence_based_macromolecule') or {})

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        props = self.properties
        out: dict[str, Any] = {key: props.get(key) for key in SBMM_FIELDS}
        for q in SBMM_QUANTITIES:
            pair = props.get(q) or {}
            out[f'{q}_value'] = pair.get('value')
            if pair.get('unit') is not None:
                out[f'{q}_unit'] = pair.get('unit')
        # Both create and update require the protein's attributes. They identify the existing
        # record unchanged, so the server leaves it alone (verified on ELN 4.0.1).
        out['sequence_based_macromolecule_attributes'] = self._macromolecule_identity()
        return out | (serialize_data or {})

    def _macromolecule_identity(self) -> dict:
        m = cast(dict, self.json_data).get('sequence_based_macromolecule') or {}
        derivation = m.get('uniprot_derivation')
        identity: dict[str, Any] = {'sbmm_type': m.get('sbmm_type') or 'protein',
                                    'uniprot_derivation': derivation}
        if m.get('sbmm_subtype'):
            identity['sbmm_subtype'] = m['sbmm_subtype']
        if derivation == 'uniprot':
            identity['primary_accession'] = m.get('primary_accession')
            return identity
        # A protein described by hand (created in the web UI): send back exactly what was loaded.
        for key in ('short_name', 'sequence', 'own_identifier', 'other_identifier', 'ec_numbers',
                    'molecular_weight', 'link_pdb', 'pdb_doi'):
            if m.get(key) is not None:
                identity[key] = m[key]
        if m.get('full_name') is not None:
            identity['full_name'] = m['full_name']
        if derivation == 'uniprot_modified':
            parent = m.get('parent') or {}
            identity['parent_identifier'] = parent.get('primary_accession') or str(parent.get('id', ''))
        identity['protein_sequence_modification_attributes'] = _strip(m.get('protein_sequence_modifications'))
        identity['post_translational_modification_attributes'] = _strip(m.get('post_translational_modifications'))
        return identity


def _strip(record) -> dict:
    return {k: v for k, v in (record or {}).items() if k not in _IDENTITY_SKIP}
