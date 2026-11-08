"""Device descriptions: lab instruments documented as elements (``/api/v1/device_descriptions``, M4.3)."""
from __future__ import annotations

from typing import Any, cast

from chemotion_api.connection import request_error
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.registry import register_element_type

#: The fields of a device description (``device_description_api.rb``'s default params). Most are
#: strings; ``general_tags`` is a list of strings, ``operators``, ``contact_for_maintenance``,
#: ``planned_maintenance``, ``consumables_needed_for_maintenance`` and ``unexpected_maintenance``
#: are lists of dicts, ``setup_descriptions`` is a dict, ``helpers_uploaded`` a bool and the two
#: ``version_installation_*_date`` values ISO dates.
FIELDS = (
    'name', 'short_label', 'device_id', 'device_type_name', 'device_type_id', 'device_type_id_type', 'device_class',
    'device_class_detail', 'operation_mode', 'vendor_device_name', 'vendor_device_id', 'serial_number',
    'vendor_company_name', 'vendor_id', 'vendor_id_type', 'description', 'general_tags', 'version_number',
    'version_installation_start_date', 'version_installation_end_date', 'version_identifier_type', 'version_doi',
    'version_doi_url', 'version_characterization', 'operators', 'owner_institution', 'owner_email', 'owner_id',
    'owner_id_type', 'inventory_id', 'alternative_identifier', 'university_campus', 'institute', 'building', 'room',
    'infrastructure_assignment', 'access_options', 'access_comments', 'size', 'weight', 'weight_unit',
    'application_name', 'application_version', 'vendor_url', 'helpers_uploaded', 'policies_and_user_information',
    'description_for_methods_part', 'ontologies', 'setup_descriptions', 'maintenance_contract_available',
    'maintenance_scheduling', 'contact_for_maintenance', 'planned_maintenance', 'consumables_needed_for_maintenance',
    'unexpected_maintenance', 'measures_after_full_shut_down', 'measures_after_short_shut_down',
    'measures_to_plan_offline_period', 'restart_after_planned_offline_period',
)
_LISTS = ('general_tags', 'operators', 'contact_for_maintenance', 'planned_maintenance',
          'consumables_needed_for_maintenance', 'unexpected_maintenance', 'ontologies')


@register_element_type('device_description', url='/api/v1/device_descriptions')
class DeviceDescription(AbstractElement):
    """
    A device description: one instrument, with its vendor, version, location, operators,
    maintenance records and ontology terms. It extends
    :class:`chemotion_api.elements.abstract_element.AbstractElement`, so analyses, segments and
    attachments work as for other elements.

    ``properties`` holds :data:`FIELDS`. ``ancestor_ids`` lists the device descriptions this one
    was split from (see ``collection.split_device_descriptions()``).

    Usage::

    >>> dev = collection.new_device_description()
    >>> dev.properties.update(name='NMR 400', vendor_company_name='Bruker', room='1.23')
    >>> dev.properties['operators'] = [{'name': 'Ada Lovelace', 'email': 'ada@example.org', 'type': 'technical'}]
    >>> dev.save()
    """

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        props: dict[str, Any] = {key: data.get(key) for key in FIELDS}
        for key in _LISTS:
            props[key] = props[key] or []
        props['setup_descriptions'] = props['setup_descriptions'] or {}
        return props

    @property
    def ancestor_ids(self) -> list[int]:
        """The device descriptions this one was split from, nearest last."""
        return list(cast(dict, self.json_data).get('ancestor_ids') or [])

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        out: dict[str, Any] = {}
        for key in FIELDS:
            value = self.properties.get(key)
            if value is None or (key in ('version_installation_start_date', 'version_installation_end_date')
                                 and value == ''):
                continue
            out[key] = value
        return out

    def download_analyses(self, file_path: str) -> str:
        """
        Saves the files of all analyses as one ZIP (``GET /api/v1/attachments/device_description_analyses/:id``).

        :return: ``file_path``
        :raises ConnectionError: when the server instead builds the archive in the background
            (large analyses) and announces it as a notification.
        """
        res = self._session.get(f'/api/v1/attachments/device_description_analyses/{self._saved_id_for("analyses")}')
        if res.status_code != 200:
            raise request_error(res, f'downloading the analyses of device description {self.id}')
        if 'zip' not in (res.headers.get('Content-Type') or '') and not res.content.startswith(b'PK'):
            raise ConnectionError('The server is preparing the archive in the background; it will send a '
                                  'notification with the download link.')
        with open(file_path, 'wb') as f:
            f.write(res.content)
        return file_path


def ontologies(session) -> list[dict]:
    """The ontology terms device descriptions can be tagged with, as offered by the segment klasses
    (``GET /api/v1/device_descriptions/ontologies``)."""
    res = session.get('/api/v1/device_descriptions/ontologies')
    if res.status_code != 200:
        raise request_error(res, 'loading the device ontologies')
    return res.json() or []
