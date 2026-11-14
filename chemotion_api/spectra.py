"""Spectra processing through the ELN's ChemSpectra service (M5.1).

The ELN converts measurement files to JCAMP-DX, picks peaks, writes processed spectra and renders
combined images by calling its configured ChemSpectra service. These functions start that work
from a script, as the UI's spectra editor does. Results come back base64-encoded; they are
returned decoded.

Most calls need the service to be running and reachable from the ELN.
"""
from __future__ import annotations

import base64
import os
from urllib.parse import urljoin
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: Peak-editor parameters ``save_spectrum`` and ``infer`` take, all strings as the UI sends them
#: (``peaks_str``, ``shift_*``, ``integration`` and ``multiplicity`` are JSON or the editor's
#: text formats).
SPECTRUM_PARAMS = (
    'peaks_str', 'shift_select_x', 'shift_ref_name', 'shift_ref_value', 'integration', 'multiplicity', 'mass',
    'scan', 'thres', 'predict', 'keep_pred', 'waveLength', 'cyclicvolta', 'curveIdx', 'simulatenmr', 'axesUnits',
    'detector', 'dscMetaData', 'lcms_uvvis_wavelength', 'lcms_mz_page', 'lcms_peaks_str', 'lcms_integrals_str',
    'peaks', 'shift', 'layout',
)


@dataclass
class SpectrumFile:
    """A spectrum file returned by the server: the attachment and its decoded content."""
    id: int | None
    content: bytes | None
    state: str | None = None
    predictions: Any = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SpectrumFile:
        encoded = data.get('file')
        return cls(id=data.get('id'), content=base64.b64decode(encoded) if encoded else None,
                   state=data.get('aasm_state'), predictions=data.get('predictions'), raw=data)


def _id(attachment) -> int:
    return attachment if isinstance(attachment, int) else attachment['id']


def _check(params: dict) -> dict:
    unknown = set(params) - set(SPECTRUM_PARAMS)
    if unknown:
        raise ValueError(f'Unknown spectrum parameters: {", ".join(sorted(unknown))}')
    return params


def save_spectrum(session: Connection, attachment, **params) -> SpectrumFile:
    """Write a processed spectrum (peaks, shift reference, integration, …) as a new JCAMP-DX
    attachment next to ``attachment`` (``POST /api/v1/attachments/save_spectrum``).

    :param params: any of :data:`SPECTRUM_PARAMS`.
    :raises ValueError: if the service could not generate the spectrum.
    """
    res = session.post('/api/v1/attachments/save_spectrum', data={'attachment_id': _id(attachment)} | _check(params))
    if res.status_code == 401:
        raise PermissionError(f'You may not edit attachment {_id(attachment)}.')
    if res.status_code == 422:
        raise ValueError(f'The spectrum of attachment {_id(attachment)} could not be generated.')
    if res.status_code not in (200, 201):
        raise request_error(res, f'saving the spectrum of attachment {_id(attachment)}')
    return SpectrumFile.from_json((res.json().get('files') or [{}])[0])


def infer_spectrum(session: Connection, attachment, **params) -> tuple[SpectrumFile, Any]:
    """Have the service predict and check the spectrum against the sample's structure
    (``POST /api/v1/attachments/infer``).

    :return: the generated JCAMP-DX file and the prediction.
    """
    res = session.post('/api/v1/attachments/infer', data={'attachment_id': _id(attachment)} | _check(params))
    if res.status_code == 401:
        raise PermissionError(f'You may not edit attachment {_id(attachment)}.')
    if res.status_code == 422:
        raise ValueError(f'The spectrum of attachment {_id(attachment)} could not be inferred.')
    if res.status_code not in (200, 201):
        raise request_error(res, f'inferring the spectrum of attachment {_id(attachment)}')
    data = res.json()
    return SpectrumFile.from_json((data.get('files') or [{}])[0]), data.get('predict')


def regenerate_spectra(session: Connection, original, generated=()) -> None:
    """Reprocess spectra from their original files, as the spectra editor's *Regenerate* does
    (``POST /api/v1/attachments/regenerate_spectrum``). The ``generated`` attachments (earlier
    results) are deleted, and the ``original`` ones are queued for conversion again; attachments
    you may not edit, or that cannot be regenerated, are skipped.
    """
    body = {'original': [_id(a) for a in original], 'generated': [_id(a) for a in generated]}
    if not body['original']:
        raise ValueError('Name the original spectra to regenerate.')
    res = session.post('/api/v1/attachments/regenerate_spectrum', data=body)
    if res.status_code not in (200, 201):
        raise request_error(res, 'regenerating spectra')


def regenerate_edited_spectra(session: Connection, edited, molfile: str | None = None) -> None:
    """Re-render edited JCAMP-DX spectra, optionally against a new structure
    (``POST /api/v1/attachments/regenerate_edited_spectrum``)."""
    body: dict[str, Any] = {'edited': [_id(a) for a in edited]}
    if not body['edited']:
        raise ValueError('Name the edited spectra to regenerate.')
    if molfile is not None:
        body['molfile'] = molfile
    res = session.post('/api/v1/attachments/regenerate_edited_spectrum', data=body)
    if res.status_code not in (200, 201):
        raise request_error(res, 'regenerating edited spectra')


def lcms_page(session: Connection, attachment, retention_time: float, polarity: str | None = None) -> dict:
    """One mass spectrum of an LC-MS run, the one closest to ``retention_time``, read from the
    run's mz JCAMP-DX files (``POST /api/v1/attachments/lcms_page``).

    :param attachment: the run's UV/Vis JCAMP-DX attachment.
    :param polarity: ``'positive'`` or ``'negative'``; anything else does not filter.
    :return: ``{'id', 'content' (bytes), 'polarity', 'page_value', …}``.
    :raises LookupError: if no page matches.
    """
    body: dict[str, Any] = {'attachment_id': _id(attachment), 'retention_time': str(retention_time)}
    if polarity is not None:
        body['polarity'] = polarity
    res = session.post('/api/v1/attachments/lcms_page', data=body)
    if res.status_code == 403:
        raise PermissionError(f'You may not read attachment {_id(attachment)}.')
    if res.status_code in (404, 422):
        raise LookupError(f'No LC-MS page of attachment {_id(attachment)} at {retention_time}: {res.text}')
    if res.status_code not in (200, 201):
        raise request_error(res, 'loading an LC-MS page')
    page = dict(res.json().get('file') or {})
    encoded = page.pop('file', None)
    page['content'] = base64.b64decode(encoded) if encoded else None
    return page


def convert_spectrum(session: Connection, file_path: str, mass: float | str = 0, molfile: str | None = None
                     ) -> tuple[bytes, bytes]:
    """Convert a measurement file to JCAMP-DX without storing anything
    (``POST /api/v1/chemspectra/file/convert``).

    :param mass: the molecular mass, for mass spectra.
    :return: the JCAMP-DX file and its rendered image.
    :raises ValueError: if the service cannot convert the file.
    """
    data: dict[str, Any] = {'mass': str(mass)}
    files: dict[str, Any] = {}
    with open(file_path, 'rb') as f:
        files['file'] = (os.path.basename(file_path), f)
        if molfile is not None:
            files['molfile'] = ('molfile.mol', molfile.encode())
        res = session.post('/api/v1/chemspectra/file/convert', data=data, files=files)
    if res.status_code not in (200, 201):
        raise request_error(res, f'converting {file_path}')
    answer = res.json()
    if not answer.get('status'):
        raise ValueError(f'The spectra service could not convert {file_path}.')
    return base64.b64decode(answer['jcamp']), base64.b64decode(answer['img'])


def combine_spectra(session: Connection, spectra, front_index: int = 0, extras: str | None = None) -> None:
    """Render several spectra into one image, stored as ``<analysis>.new_combined.png`` in the
    last spectrum's dataset (``POST /api/v1/chemspectra/file/combine_spectra``).

    :param spectra: JCAMP-DX attachments, in drawing order.
    :param front_index: which of them is drawn in front.
    """
    ids = [_id(a) for a in spectra]
    if not ids or not 0 <= front_index < len(ids):
        raise ValueError('Give the spectra and the index of the front one.')
    body: dict[str, Any] = {'spectra_ids': ids, 'front_spectra_idx': front_index}
    if extras is not None:
        body['extras'] = extras
    res = session.post('/api/v1/chemspectra/file/combine_spectra', data=body)
    if res.status_code == 401:
        raise PermissionError('You may not read every spectrum, or not edit the last one.')
    if res.status_code == 422:
        raise ValueError('The last spectrum must belong to an analysis.')
    if res.status_code not in (200, 201):
        raise request_error(res, 'combining spectra')


def spectra_layouts(session: Connection) -> Any:
    """The spectra service's layouts and data types, compared with the ELN's (admins only;
    ``GET /api/v1/chemspectra/spectra_layouts``)."""
    res = session.get('/api/v1/chemspectra/spectra_layouts')
    if res.status_code == 401:
        raise PermissionError('Only admins can read the spectra layouts.')
    if res.status_code != 200:
        raise request_error(res, 'loading the spectra layouts')
    return res.json()


def nmrium_url(session: Connection) -> str | None:
    """The NMRium editor the ELN links to, or ``None`` (``GET /api/v1/chemspectra/nmrium_wrapper/:host``).

    ELN v4.0.1 answers with a path on the ELN itself (``/nmrium/v1.2.0/``); it is resolved against
    the ELN's address, so the result is always an absolute URL.
    """
    # The host name is part of the route but unused by the server; a dotted one would be cut at
    # the first dot (Grape reads it as a format suffix).
    res = session.get('/api/v1/chemspectra/nmrium_wrapper/eln')
    if res.status_code != 200:
        raise request_error(res, 'loading the NMRium address')
    url = res.json().get('nmrium_url')
    return urljoin(session.host_url + '/', url) if url else None


class Spectra:
    """The spectra functions bound to a connection; ``instance.spectra()`` returns one.

    >>> spectra = instance.spectra()
    >>> result = spectra.save(jcamp_attachment, peaks_str='7.26,100', shift_ref_name='CDCl3')
    >>> spectra.combine([ir_a, ir_b], front_index=1)
    """

    def __init__(self, session: Connection):
        self._session = session

    def save(self, attachment, **params) -> SpectrumFile:
        """See :func:`save_spectrum`."""
        return save_spectrum(self._session, attachment, **params)

    def infer(self, attachment, **params) -> tuple[SpectrumFile, Any]:
        """See :func:`infer_spectrum`."""
        return infer_spectrum(self._session, attachment, **params)

    def regenerate(self, original, generated=()) -> None:
        """See :func:`regenerate_spectra`."""
        regenerate_spectra(self._session, original, generated)

    def regenerate_edited(self, edited, molfile: str | None = None) -> None:
        """See :func:`regenerate_edited_spectra`."""
        regenerate_edited_spectra(self._session, edited, molfile)

    def lcms_page(self, attachment, retention_time: float, polarity: str | None = None) -> dict:
        """See :func:`lcms_page`."""
        return lcms_page(self._session, attachment, retention_time, polarity)

    def convert(self, file_path: str, mass: float | str = 0, molfile: str | None = None) -> tuple[bytes, bytes]:
        """See :func:`convert_spectrum`."""
        return convert_spectrum(self._session, file_path, mass, molfile)

    def combine(self, spectra, front_index: int = 0, extras: str | None = None) -> None:
        """See :func:`combine_spectra`."""
        combine_spectra(self._session, spectra, front_index, extras)

    def layouts(self) -> Any:
        """See :func:`spectra_layouts`."""
        return spectra_layouts(self._session)

    def nmrium_url(self) -> str | None:
        """See :func:`nmrium_url`."""
        return nmrium_url(self._session)
