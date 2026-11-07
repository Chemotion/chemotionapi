"""Reports, report archives and table exports (M3.2).

Three kinds of output the UI offers:

* **Reports** (the *Report* tab): a docx (or xlsx/csv/html reaction list) generated from samples
  and reactions with one of the server's templates. The server generates it in a background job;
  the result is kept as an :class:`Archive` of yours until you delete it. See
  :func:`create_report` / ``instance.create_report()``.
* **Table exports** of selected elements (the list's *Export* dialogs): an XLSX or SDF file of
  samples (with their reactions and wellplates), or a CSV of reaction SMILES. See
  ``collection.export_elements()`` and ``collection.export_reaction_smiles()``.
* **Per-element files**: a reaction as a docx (``reaction.report_docx()``) and the samples of a
  reaction or wellplate as XLSX (``export_samples_excel()``).
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: Report types (``ReportTemplate::REPORT_TYPES``) and the extension of the file each produces.
REPORT_TYPES = {
    'standard': 'docx',
    'spectrum': 'docx',
    'supporting_information': 'docx',
    'supporting_information_std_rxn': 'docx',
    'rxn_list_xlsx': 'xlsx',
    'rxn_list_csv': 'csv',
    'rxn_list_html': 'html',
}

#: Report settings and their UI defaults (all on). Keys are the server's names.
SAMPLE_SETTINGS = ('diagram', 'collection', 'analyses', 'reaction_description', 'literature')
REACTION_SETTINGS = ('diagram', 'material', 'description', 'purification', 'dangerous_products', 'tlc',
                     'observation', 'analysis', 'literature', 'variations')
SI_REACTION_SETTINGS = ('Name', 'CAS', 'Formula', 'Smiles', 'InChI', 'Molecular Mass', 'Exact Mass', 'EA')

#: The UI export dialog's preselected columns, per table. Other column names the server knows are
#: listed in the dialog (``ModalExport.js``); e.g. ``'molfile'``, ``'description'``,
#: ``'molecular_weight'``, and the ``analyses``, ``chemicals`` and ``components`` tables.
DEFAULT_EXPORT_COLUMNS: dict[str, list[str]] = {
    'sample': ['cas', 'name', 'external_label', 'real_amount_value', 'real_amount_unit', 'created_at'],
    'molecule': ['cano_smiles'],
    'reaction': ['name', 'short_label'],
    'wellplate': [],
    'analyses': [],
    'chemicals': [],
    'components': [],
}

#: Export formats of ``export_samples_from_selections`` (``exportType``).
EXPORT_FORMATS = {'xlsx': 1, 'sdf': 2}

#: Reaction SMILES notations of the reaction export (``exportType`` 0-6): SM starting
#: materials, R reactants, S solvents, P products.
REACTION_SMILES_NOTATIONS = {
    'SM>>P': 0, 'SM.R>>P': 1, 'SM.R.S>>P': 2, 'SM>R>P': 3, 'SM>R.S>P': 4, 'SM>R>S>P': 5, 'SM,R,S,P': 6,
}

#: Element types a report can contain.
REPORTABLE_TYPES = ('sample', 'reaction')


@dataclass
class ReportTemplate:
    """A report template of the server (``GET /api/v1/report_templates``)."""
    id: int
    name: str
    report_type: str


@dataclass
class Archive:
    """A generated report, as the UI's *Archive* tab lists it.

    :attr:`downloadable` turns true once the server's background job has written the file.
    """
    id: int
    file_name: str
    template: str | None
    downloadable: bool
    file_description: str | None = None
    objects: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _session: Connection | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: dict[str, Any], session: Connection | None = None) -> Archive:
        return cls(id=data['id'], file_name=data.get('file_name') or '', template=data.get('template'),
                   downloadable=bool(data.get('downloadable')), file_description=data.get('file_description'),
                   objects=data.get('objects') or [], raw=data, _session=session)

    @property
    def extension(self) -> str:
        return REPORT_TYPES.get(self.template or '', 'docx')

    def _con(self) -> Connection:
        if self._session is None:
            raise ValueError('This archive is not attached to a server connection.')
        return self._session

    def refresh(self) -> Archive:
        """Reload this archive's state (e.g. :attr:`downloadable`) from the server."""
        for found in archives(self._con()):
            if found.id == self.id:
                self.__dict__.update({k: v for k, v in found.__dict__.items()})
                return self
        raise ConnectionError(f'Report archive {self.id} no longer exists.')

    def download(self, file_path: str) -> str:
        """Save the report to ``file_path``. ``GET /api/v1/download_report/file``.

        :raises ValueError: if the report is not generated yet (see :func:`wait_until_downloadable`).
        """
        if not self.downloadable:
            raise ValueError(f'Report "{self.file_name}" is not generated yet.')
        res = self._con().get('/api/v1/download_report/file', params={'id': self.id, 'ext': self.extension})
        if res.status_code != 200:
            raise request_error(res, f'downloading report {self.id}')
        with open(file_path, 'wb') as f:
            f.write(res.content)
        return file_path

    def delete(self) -> None:
        """Delete this report and its file. ``DELETE /api/v1/archives/:id``."""
        res = self._con().delete(f'/api/v1/archives/{self.id}')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting report {self.id}')


def report_templates(session: Connection) -> list[ReportTemplate]:
    res = session.get('/api/v1/report_templates')
    if res.status_code != 200:
        raise request_error(res, 'loading the report templates')
    return [ReportTemplate(t['id'], t.get('name') or '', t.get('report_type') or '')
            for t in res.json().get('templates') or []]


def archives(session: Connection) -> list[Archive]:
    res = session.get('/api/v1/archives/all')
    if res.status_code != 200:
        raise request_error(res, 'loading your report archives')
    return [Archive.from_json(a, session) for a in res.json().get('archives') or []]


def _settings(names: tuple[str, ...], values: Mapping[str, bool] | None) -> list[dict[str, Any]]:
    values = dict(values or {})
    unknown = set(values) - set(names)
    if unknown:
        raise ValueError(f'Unknown report settings {", ".join(sorted(unknown))}; use {", ".join(names)}.')
    return [{'text': name, 'checked': bool(values.get(name, True))} for name in names]


def report_payload(elements: Iterable, template: str | int | ReportTemplate = 'standard', *,
                   file_name: str | None = None, description: str | None = None,
                   sample_settings: Mapping[str, bool] | None = None,
                   reaction_settings: Mapping[str, bool] | None = None,
                   si_reaction_settings: Mapping[str, bool] | None = None,
                   page_break: bool = True, all_chemicals_in_schemes: bool = True,
                   image_format: str = 'png', molecule_serials: Mapping[int, str] | None = None) -> dict:
    """The body of ``POST /api/v1/reports`` (see :func:`create_report`)."""
    objects = []
    for element in elements:
        if element.element_type not in REPORTABLE_TYPES:
            raise ValueError(f'Reports hold samples and reactions only, not {element.element_type} elements.')
        if element.id is None:
            raise ValueError('Save the element before adding it to a report.')
        objects.append({'id': element.id, 'type': element.element_type})
    if not objects:
        raise ValueError('A report needs at least one sample or reaction.')
    if isinstance(template, ReportTemplate):
        template_id, template_type = str(template.id), template.report_type
    elif isinstance(template, int):
        template_id, template_type = str(template), None
    elif template in REPORT_TYPES:
        template_id, template_type = template, template
    else:
        raise ValueError(f'Unknown report type {template!r}; use one of {", ".join(REPORT_TYPES)}, '
                         'or a template from report_templates().')
    if image_format not in ('png', 'eps', 'emf'):
        raise ValueError('image_format is png, eps or emf.')
    payload = {
        'objTags': objects,
        'splSettings': _settings(SAMPLE_SETTINGS, sample_settings),
        'rxnSettings': _settings(REACTION_SETTINGS, reaction_settings),
        'siRxnSettings': _settings(SI_REACTION_SETTINGS, si_reaction_settings),
        # The UI sends 'whole_diagram' when checked and 'product_diagram' (checked) otherwise.
        'configs': [{'text': 'page_break', 'checked': page_break},
                    {'text': 'whole_diagram', 'checked': True} if all_chemicals_in_schemes
                    else {'text': 'product_diagram', 'checked': True}],
        'molSerials': [{'mol': {'id': mol_id}, 'value': value} for mol_id, value in (molecule_serials or {}).items()],
        'prdAtts': [],
        'imgFormat': image_format,
        'fileName': file_name or f'ELN_Report_{time.strftime("%Y-%m-%dT%H-%M-%S")}',
        'templateId': template_id,
    }
    if template_type:
        payload['templateType'] = template_type
    if description is not None:
        payload['fileDescription'] = description
    return payload


def create_report(session: Connection, elements: Iterable, template: str | int | ReportTemplate = 'standard', *,
                  wait: bool = True, timeout: float = 300, poll_interval: float = 3, **options) -> Archive:
    """Generate a report, as the UI's *Report* tab does. ``POST /api/v1/reports``.

    The server queues the generation (it starts about 30 s later) and keeps the result as an
    :class:`Archive`. With ``wait`` this polls until the file is ready.

    :param elements: the samples and reactions, in report order.
    :param template: a report type from :data:`REPORT_TYPES`, a template id, or a
        :class:`ReportTemplate`.
    :param options: see :func:`report_payload`: ``file_name``, ``description``, ``sample_settings``
        / ``reaction_settings`` / ``si_reaction_settings`` (``{setting: bool}``, all on by
        default), ``page_break``, ``all_chemicals_in_schemes``, ``image_format`` and
        ``molecule_serials`` (``{molecule_id: 'serial'}`` for supporting-information reports).
    :raises PermissionError: if you may not read one of the elements.
    :raises TimeoutError: if the report is not ready within ``timeout`` seconds.
    """
    res = session.post('/api/v1/reports', data=report_payload(elements, template, **options))
    if res.status_code == 401:
        raise PermissionError('You may not read every element of the report.')
    if res.status_code not in (200, 201):
        raise request_error(res, 'creating a report')
    archive = Archive.from_json(res.json()['report'], session)
    if wait and not archive.downloadable:
        wait_until_downloadable(archive, timeout, poll_interval)
    return archive


def wait_until_downloadable(archive: Archive, timeout: float = 300, poll_interval: float = 3) -> Archive:
    """Poll ``POST /api/v1/archives/downloadable`` until the report's file is ready."""
    session = archive._con()
    deadline = time.monotonic() + timeout
    while True:
        res = session.post('/api/v1/archives/downloadable', data={'ids': [archive.id]})
        if res.status_code not in (200, 201):
            raise request_error(res, f'checking report {archive.id}')
        for data in res.json().get('archives') or []:
            if data.get('id') == archive.id:
                ready = Archive.from_json(data, session)
                archive.__dict__.update(ready.__dict__)
                return archive
        if time.monotonic() >= deadline:
            raise TimeoutError(f'Report "{archive.file_name}" was not generated within {timeout} s; '
                               'it may still be queued on the server.')
        time.sleep(poll_interval)


def _selection_state(elements: Iterable, collection_id: int) -> dict[str, Any]:
    from chemotion_api.elements.abstract_element import ui_state_selection
    selection = ui_state_selection(list(elements), 'export it')
    state: dict[str, Any] = {}
    for kind in ('sample', 'reaction', 'wellplate'):
        state[kind] = {'checkedIds': selection.pop(kind, {}).get('checkedIds', []), 'uncheckedIds': [],
                       'checkedAll': False}
    if selection:
        raise ValueError(f'Only samples, reactions and wellplates can be exported this way, not '
                         f'{", ".join(sorted(selection))}.')
    state['currentCollection'] = collection_id
    return state


def _write_binary(res, file_path: str, what: str) -> str | None:
    if res.status_code == 204:
        return None
    if res.status_code not in (200, 201):
        raise request_error(res, what)
    with open(file_path, 'wb') as f:
        f.write(res.content)
    return file_path


def export_elements(session: Connection, collection_id: int, elements: Iterable, file_path: str,
                    file_format: str = 'xlsx', columns: Mapping[str, list[str]] | None = None) -> str | None:
    if file_format not in EXPORT_FORMATS:
        raise ValueError(f'file_format is one of {", ".join(EXPORT_FORMATS)}.')
    cols = {table: list(values) for table, values in (columns if columns is not None else DEFAULT_EXPORT_COLUMNS).items()}
    unknown = set(cols) - set(DEFAULT_EXPORT_COLUMNS)
    if unknown:
        raise ValueError(f'Unknown export tables {", ".join(sorted(unknown))}; use {", ".join(DEFAULT_EXPORT_COLUMNS)}.')
    body = {'exportType': EXPORT_FORMATS[file_format], 'uiState': _selection_state(elements, collection_id),
            'columns': cols}
    res = session.post('/api/v1/reports/export_samples_from_selections', data=body)
    return _write_binary(res, file_path, f'exporting elements of collection {collection_id}')


def export_reaction_smiles(session: Connection, collection_id: int, reactions: Iterable, file_path: str,
                           notation: str = 'SM>R>P') -> str | None:
    if notation not in REACTION_SMILES_NOTATIONS:
        raise ValueError(f'notation is one of {", ".join(REACTION_SMILES_NOTATIONS)}.')
    reactions = list(reactions)
    if any(r.element_type != 'reaction' for r in reactions):
        raise ValueError('Only reactions can be exported as reaction SMILES.')
    body = {'exportType': REACTION_SMILES_NOTATIONS[notation], 'uiState': _selection_state(reactions, collection_id),
            'columns': {}}
    res = session.post('/api/v1/reports/export_reactions_from_selections', data=body)
    return _write_binary(res, file_path, f'exporting reaction SMILES of collection {collection_id}')


def download_to(session: Connection, url: str, params: dict, file_path: str, what: str) -> str:
    res = session.get(url, params=params)
    if res.status_code != 200:
        raise request_error(res, what)
    with open(file_path, 'wb') as f:
        f.write(res.content)
    return file_path
