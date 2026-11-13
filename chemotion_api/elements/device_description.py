"""Device descriptions: the v4 element type recording an instrument and how it is run.

Unlike every other element, a device description carries its **own ontology annotations**:
an admin picks terms for it from the TIB Terminology Service, and each stored entry already
holds a full IRI. That makes it the only element whose ontology terms need no resolution
chain at all — see :meth:`DeviceDescription.ontology_terms`.
"""
from typing import cast

from chemotion_api.elements.abstract_element import AbstractElement

#: Scalar fields the ELN exposes as ``properties``. Deliberately not the whole entity:
#: `container`, `attachments`, `segments` and `comments` are handled by the base class, and
#: `ontologies` has its own accessor. Fields not listed here still survive a save (see
#: :meth:`DeviceDescription._clean_properties_data`).
DEVICE_FIELDS = (
    'name', 'short_label', 'description',
    'device_type_name', 'device_type_id', 'device_type_id_type',
    'device_class', 'device_class_detail', 'operation_mode',
    'vendor_device_name', 'vendor_device_id', 'vendor_company_name', 'serial_number',
    'version_number', 'version_doi', 'version_doi_url', 'version_characterization',
    'version_installation_start_date', 'version_installation_end_date',
    'owner_institution', 'university_campus', 'institute', 'building', 'room',
    'application_name', 'application_version', 'vendor_url',
    'general_tags', 'operators',
)


class DeviceDescription(AbstractElement):
    """A Chemotion *device description* — an instrument, its vendor, version and siting.

    Usage::

        >>> for device in collection.get_device_descriptions():
        ...     print(device.properties['name'], device.ontology_terms())
    """

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        return {key: data.get(key) for key in DEVICE_FIELDS}

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        serialize_data = serialize_data if serialize_data is not None else {}
        data = cast(dict, self.json_data)
        # Start from the server's own record so fields this client does not model (there are
        # ~50 more on the entity, from maintenance scheduling to shut-down procedures) survive
        # a save instead of being dropped by a round trip through a narrower model.
        out = dict(data)
        for key in DEVICE_FIELDS:
            if key in self.properties:
                out[key] = self.properties.get(key)
        return out | serialize_data

    def ontology_terms(self) -> list[dict]:
        """The device's ontology annotations as ``{"iri": …, "label": …}``.

        The ELN stores these as a list of ``{"data": {...}, "segments": [...], ...}`` entries
        whose ``data`` comes straight from the **TIB Terminology Service**, so each already
        carries a resolvable ``iri`` and its ``label``. Nothing needs looking up.

        Entries flagged ``is_deleted`` are dropped — the ELN keeps them in the column so the
        UI can show an undo; they are no longer annotations of the device.
        """
        terms: list[dict] = []
        seen: set[str] = set()
        for entry in (cast(dict, self.json_data).get('ontologies') or []):
            if not isinstance(entry, dict) or entry.get('is_deleted'):
                continue
            data = entry.get('data')
            if not isinstance(data, dict):
                continue
            iri = data.get('iri')
            if not isinstance(iri, str) or not iri.strip() or iri in seen:
                continue
            seen.add(iri)
            label = data.get('label')
            terms.append({
                'iri': iri.strip(),
                'label': label.strip() if isinstance(label, str) and label.strip()
                else (data.get('short_form') or data.get('obo_id') or iri),
            })
        return terms
