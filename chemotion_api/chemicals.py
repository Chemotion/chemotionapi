"""Chemical inventory data and safety data sheets of samples (M4.5).

A sample (or SBMM sample) kept in the chemical inventory has a ``Chemical`` record: its CAS number
and ``chemical_data``, a one-entry list whose dict holds the inventory fields the UI's *Inventory*
tab edits — ``status``, ``vendor``, ``amount``, storage location, dates, ``h_statements`` /
``p_statements`` / ``pictograms``, and ``safetySheetPath`` (the saved safety data sheets). Inventory
*labels* (prefix and counter for inventory sample labels) belong to collections.
``/api/v1/chemicals``, ``/api/v1/inventory``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: Safety data sheet vendors the server can search.
SDS_VENDORS = ('Merck', 'Thermofisher', 'All')


@dataclass
class Chemical:
    """The chemical record of one sample. ``data`` is ``chemical_data[0]``."""
    id: int | None = None
    cas: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    sample_id: int | None = None
    sbmm_sample_id: int | None = None

    @property
    def safety_sheets(self) -> list[str]:
        """The paths of the saved safety data sheets (``/safety_sheets/<vendor>/<file>.pdf``)."""
        return [path for entry in self.data.get('safetySheetPath') or [] for path in entry.values()]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Chemical:
        entries = data.get('chemical_data') or [{}]
        return cls(id=data.get('id'), cas=data.get('cas'), data=dict(entries[0] or {}), sample_id=data.get('sample_id'),
                   sbmm_sample_id=data.get('sequence_based_macromolecule_sample_id'))


def _owner(element) -> dict[str, int]:
    kind = getattr(element, 'element_type', None)
    if getattr(element, 'id', None) is None:
        raise ValueError('Save the sample first.')
    if kind == 'sample':
        return {'sample_id': element.id}
    if kind == 'sequence_based_macromolecule_sample':
        return {'sequence_based_macromolecule_sample_id': element.id}
    raise ValueError('Only samples and SBMM samples have chemical data.')


def load_chemical(session: Connection, element) -> Chemical | None:
    """The element's chemical record, or ``None`` if it has none (``GET /api/v1/chemicals``)."""
    res = session.get('/api/v1/chemicals', params=_owner(element))
    if res.status_code == 401:
        raise PermissionError('You need full read access to the sample to see its chemical data.')
    if res.status_code != 200:
        raise request_error(res, 'loading chemical data')
    chemical = Chemical.from_json(res.json() or {})
    return chemical if chemical.id is not None else None


def save_chemical(session: Connection, element, chemical: Chemical) -> Chemical:
    """Create the element's chemical record, or update it (``POST /chemicals/create``, ``PUT /chemicals``)."""
    owner = _owner(element)
    body: dict[str, Any] = owner | {'chemical_data': [chemical.data]}
    if chemical.cas is not None:
        body['cas'] = chemical.cas
    if chemical.id is None:
        if not chemical.cas:
            raise ValueError('A new chemical record needs a CAS number.')
        res = session.post('/api/v1/chemicals/create', data=body)
    else:
        res = session.put('/api/v1/chemicals', data=body)
    if res.status_code == 401:
        raise PermissionError('You may not edit this sample.')
    if res.status_code not in (200, 201):
        raise request_error(res, 'saving chemical data')
    return load_chemical(session, element) or chemical


def find_safety_sheets(session: Connection, name: str | None = None, molecule_id: int | None = None,
                       vendor: str = 'All', language: str = 'en', product_number: str | None = None,
                       by: str = 'CAS') -> dict:
    """Look up safety data sheets at chemical vendors, as the *Inventory* tab's search does
    (``GET /api/v1/chemicals/fetch_safetysheet/:molecule_id``). The server queries the vendor sites.

    :param name: what to search for (a CAS number or name); without it the molecule's first CAS
        number (``by='CAS'``) or name (``by='Common Name'``) is used.
    :param vendor: ``'Merck'`` (also ``'Sigma-Aldrich'``), ``'Thermofisher'`` or ``'All'``.
    :return: the vendors' answers, e.g. ``{'merck_link': {'merck_link': url, 'merck_product_number': ...}}``.
    """
    if vendor not in SDS_VENDORS + ('Sigma-Aldrich',):
        raise ValueError(f'vendor is one of {", ".join(SDS_VENDORS)}.')
    if name is None and molecule_id is None:
        raise ValueError('Give a name or CAS number, or a molecule.')
    params = {'data[vendor]': vendor, 'data[language]': language, 'data[option]': by}
    if name:
        params['data[searchStr]'] = name
    if product_number:
        params['data[productNumber]'] = product_number
    res = session.get(f'/api/v1/chemicals/fetch_safetysheet/{molecule_id if molecule_id is not None else "null"}',
                      params=params)
    if res.status_code != 200:
        raise request_error(res, f'searching safety data sheets for {name or molecule_id}')
    return res.json()


def save_vendor_safety_sheet(session: Connection, sample, chemical: Chemical, vendor_product: str) -> Chemical:
    """Have the server download a vendor's safety data sheet and store it with the sample
    (``POST /api/v1/chemicals/save_safety_datasheet``).

    :param vendor_product: the key in ``chemical.data`` holding the vendor's product info, as
        :func:`find_safety_sheets` gave it (e.g. ``'merckProductInfo'`` with ``sdsLink``).
    """
    if not chemical.cas:
        raise ValueError('The chemical needs a CAS number.')
    owner = _owner(sample)
    if 'sample_id' not in owner:
        _sample_only()
    res = session.post('/api/v1/chemicals/save_safety_datasheet',
                       data={'sample_id': owner['sample_id'],
                             'cas': chemical.cas, 'chemical_data': [chemical.data], 'vendor_product': vendor_product})
    if res.status_code not in (200, 201):
        raise request_error(res, 'saving a vendor safety data sheet')
    return load_chemical(session, sample) or chemical


def attach_safety_sheet(session: Connection, sample, file_path: str, vendor_name: str, vendor_product: str,
                        vendor_info: dict | None = None, cas: str | None = None) -> Chemical:
    """Store a safety data sheet you have as a file with the sample, as the *Inventory* tab's
    manual upload does (``POST /api/v1/chemicals/save_manual_sds``). The chemical record is created
    if the sample has none.

    :param vendor_name: e.g. ``'Merck'``; the sheet is stored under ``/safety_sheets/<vendor_name>/``.
    :param vendor_product: the ``chemical_data`` key for the vendor info, e.g. ``'merckProductInfo'``.
    :param vendor_info: the product info to store there, e.g. ``{'productNumber': 'E7023'}``.
    """
    owner = _owner(sample)
    if 'sample_id' not in owner:
        _sample_only()
    body: dict[str, Any] = {'sample_id': owner['sample_id'], 'vendor_name': vendor_name, 'vendor_product': vendor_product,
                            'vendor_info': json.dumps(vendor_info or {})}
    if cas:
        body['cas'] = cas
    with open(file_path, 'rb') as f:
        res = session.post('/api/v1/chemicals/save_manual_sds', data=body,
                           files={'attached_file': (os.path.basename(file_path), f, 'application/pdf')})
    if res.status_code == 401:
        raise PermissionError('You may not edit this sample.')
    if res.status_code not in (200, 201):
        raise request_error(res, f'storing the safety data sheet {file_path}')
    return Chemical.from_json(res.json())


def _sample_only() -> None:
    raise ValueError('Safety data sheets are stored for samples only.')


def download_safety_sheet(session: Connection, path: str, file_path: str) -> str:
    """Save a stored safety data sheet (a :attr:`Chemical.safety_sheets` path) to ``file_path``."""
    res = session.get(path)
    if res.status_code != 200:
        raise request_error(res, f'downloading {path}')
    with open(file_path, 'wb') as f:
        f.write(res.content)
    return file_path


def extract_safety_sheet(session: Connection, path: str) -> dict:
    """Read the H and P statements and the section 9 properties out of a stored safety data sheet
    (``GET /api/v1/chemicals/extract_sds``).

    :raises ValueError: if the sheet cannot be read (e.g. a scanned PDF without text).
    :raises ConnectionError: if the server's extraction service is unavailable.
    """
    res = session.get('/api/v1/chemicals/extract_sds', params={'path': path})
    if res.status_code in (400, 404, 422):
        raise ValueError(f'Cannot read the safety data sheet {path}: {res.text}')
    if res.status_code != 200:
        raise request_error(res, f'reading the safety data sheet {path}')
    return res.json()


@dataclass
class InventoryLabel:
    """The inventory label of a group of collections: samples there get ``<prefix>-<counter>`` labels."""
    id: int | None
    prefix: str
    name: str
    counter: int


def inventory_label(session: Connection, collection_id: int) -> InventoryLabel | None:
    """The collection's inventory label, or ``None`` (``GET /api/v1/inventory/:collection_id``)."""
    res = session.get(f'/api/v1/inventory/{collection_id}')
    if res.status_code != 200:
        raise request_error(res, f'loading the inventory of collection {collection_id}')
    data = res.json()
    return InventoryLabel(data.get('id'), data['prefix'], data['name'], data['counter']) if data else None


def set_inventory_label(session: Connection, prefix: str, name: str, counter: int, collection_ids: list[int]) -> list:
    """Give collections an inventory label (``PUT /api/v1/inventory/update_inventory_label``).

    :return: your inventories and their collections afterwards.
    """
    if not collection_ids:
        raise ValueError('Name the collections to label.')
    res = session.put('/api/v1/inventory/update_inventory_label',
                      data={'prefix': prefix, 'name': name, 'counter': counter, 'collection_ids': collection_ids})
    if res.status_code != 200:
        raise request_error(res, 'setting the inventory label')
    return res.json().get('inventory_collections') or []


def inventory_collections(session: Connection) -> list[dict]:
    """Your collections grouped by inventory: ``{'inventory_id', 'inventory', 'collections'}`` dicts."""
    res = session.get('/api/v1/inventory/user_inventory_collections')
    if res.status_code != 200:
        raise request_error(res, 'loading your inventories')
    return res.json().get('inventory_collections') or []
