"""Measurements: values recorded for samples, e.g. from a research plan's table (M5.2).

A measurement is one value with unit and description, attached to a sample and to the element it
came from (its *source*, usually a research plan). ``/api/v1/measurements``.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error


@dataclass
class Measurement:
    id: int
    sample_id: int
    description: str
    value: float
    unit: str
    source_type: str | None = None
    source_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sample_short_label: str | None = None
    _session: Connection | None = field(default=None, repr=False, compare=False)

    def delete(self) -> None:
        """Delete this measurement (``DELETE /api/v1/measurements/:id``)."""
        if self._session is None:
            raise ValueError('Not attached to a server connection.')
        res = self._session.delete(f'/api/v1/measurements/{self.id}')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting measurement {self.id}')
        errors = (res.json() or {}).get('errors') if res.content else None
        if errors:
            raise ValueError(f'Measurement {self.id} was not deleted: {"; ".join(errors)}')


class MeasurementError(ValueError):
    """Some rows of :func:`create_measurements` were refused. ``results`` holds every row with its
    ``id`` (created) or ``errors``."""

    def __init__(self, results: list[dict]):
        self.results = results
        failed = [r for r in results if r.get('errors')]
        super().__init__(f'{len(failed)} of {len(results)} measurements were not created: '
                         + '; '.join(f'{r.get("sample_identifier")}: {", ".join(r["errors"])}' for r in failed))


def load_measurements(session: Connection, sample_id: int, hierarchy: bool = True, source=None) -> list[Measurement]:
    """The sample's measurements (``GET /api/v1/measurements``).

    :param hierarchy: include those of the sample's whole split family (root and all subsamples).
    :param source: only those taken from this element.
    """
    params: dict[str, Any] = {'sample_id': sample_id, 'show_hierarchy': hierarchy}
    if source is not None:
        params |= {'source_type': source.element_type, 'source_id': source.id}
    res = session.get('/api/v1/measurements', params=params)
    if res.status_code == 404:
        raise PermissionError(f'Sample {sample_id} is not in one of your collections.')
    if res.status_code != 200:
        raise request_error(res, f'loading the measurements of sample {sample_id}')
    out = []
    for entry in res.json().get('measurements') or []:
        for m in entry.get('measurements') or []:
            out.append(Measurement(id=m['id'], sample_id=entry['id'], description=m.get('description') or '',
                                   value=m.get('value'), unit=m.get('unit') or '', source_type=m.get('source_type'),
                                   source_id=m.get('source_id'), metadata=m.get('metadata') or {},
                                   sample_short_label=entry.get('short_label'), _session=session))
    return out


def create_measurements(session: Connection, source, rows: Iterable[dict]) -> list[dict]:
    """Record measurements of samples taken from ``source``, as a research plan table's
    *Create measurements* action does (``POST /api/v1/measurements/bulk_create_from_raw_data``).

    :param source: the saved element the values come from, e.g. a research plan.
    :param rows: dicts with ``sample`` (a sample or its short label), ``description``, ``value``,
        ``unit`` and optionally ``metadata``. Samples are matched by short label.
    :return: the rows as the server answered them, each with the new measurement ``id``.
    :raises MeasurementError: if any row was refused (others may have been created; see ``results``).
    """
    if getattr(source, 'id', None) is None:
        raise ValueError('Save the source element first.')
    raw = []
    for row in rows:
        sample = row.get('sample')
        label = sample if isinstance(sample, str) else getattr(sample, 'short_label', None)
        if not label or row.get('value') is None or not row.get('unit') or not row.get('description'):
            raise ValueError(f'A measurement needs sample, description, value and unit: {row!r}')
        entry = {'description': row['description'], 'sample_identifier': label, 'unit': row['unit'],
                 'value': float(row['value']), 'uuid': str(uuid.uuid4())}
        if row.get('metadata'):
            entry['metadata'] = row['metadata']
        raw.append(entry)
    if not raw:
        raise ValueError('No measurements given.')
    res = session.post('/api/v1/measurements/bulk_create_from_raw_data',
                       data={'raw_data': raw, 'source_type': source.element_type, 'source_id': source.id})
    if res.status_code not in (200, 201):
        raise request_error(res, 'creating measurements')
    results = res.json().get('measurements') or []
    if any(r.get('errors') for r in results):
        raise MeasurementError(results)
    return results
