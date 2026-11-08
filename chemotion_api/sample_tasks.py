"""Sample tasks: weighing tasks a lab device (or app) fulfils by uploading scan results (M5.5).

A task asks for ``required_scan_results`` scans — a photo of the balance with the weighed value —
for a sample. Once enough scans are in and a sample is assigned, the server finishes the task and
writes the averaged value to the sample. The feature must be enabled on the ELN
(``weighing_tasks`` UI component). ``/api/v1/sample_tasks``.
"""
from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

STATUSES = ('open', 'with_missing_scan_results', 'done')


@dataclass
class SampleTask:
    id: int
    description: str | None
    sample_id: int | None
    required_scan_results: int
    done: bool = False
    result_value: float | None = None
    result_unit: str | None = None
    scan_results: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _session: Connection | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: dict[str, Any], session: Connection | None = None) -> SampleTask:
        return cls(id=data['id'], description=data.get('description'), sample_id=data.get('sample_id'),
                   required_scan_results=data.get('required_scan_results') or 1, done=bool(data.get('done')),
                   result_value=data.get('result_value'), result_unit=data.get('result_unit'),
                   scan_results=data.get('scan_results') or [], raw=data, _session=session)

    def _con(self) -> Connection:
        if self._session is None:
            raise ValueError('Not attached to a server connection.')
        return self._session

    def update(self, description: str | None = None, sample=None) -> SampleTask:
        """Change the description or assign the sample (``PUT /sample_tasks/:id``). A task with all
        its scans and a sample is finished by the server right away."""
        body: dict[str, Any] = {}
        if description is not None:
            body['description'] = description
        if sample is not None:
            body['sample_id'] = sample if isinstance(sample, int) else sample.id
        res = self._con().put(f'/api/v1/sample_tasks/{self.id}', data=body)
        _raise(res, f'updating sample task {self.id}')
        self.__dict__.update(SampleTask.from_json(res.json(), self._session).__dict__)
        return self

    def add_scan_result(self, file_path: str, value: float, unit: str, title: str | None = None) -> dict:
        """Upload one scan (an image of the reading) with its value
        (``POST /sample_tasks/:id/scan_results``). The task is finished once all scans are in."""
        data: dict[str, Any] = {'measurement_value': value, 'measurement_unit': unit}
        if title is not None:
            data['title'] = title
        mime = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        with open(file_path, 'rb') as f:
            res = self._con().post(f'/api/v1/sample_tasks/{self.id}/scan_results', data=data,
                                   files={'file': (os.path.basename(file_path), f, mime)})
        _raise(res, f'adding a scan result to sample task {self.id}')
        return res.json()

    def delete(self) -> None:
        """Delete this open task (``DELETE /sample_tasks/:id``)."""
        res = self._con().delete(f'/api/v1/sample_tasks/{self.id}')
        if res.status_code == 400:
            raise ValueError(f'Sample task {self.id} could not be deleted (only open tasks can).')
        _raise(res, f'deleting sample task {self.id}')


def _raise(res, what: str) -> None:
    if res.status_code == 404:
        raise ConnectionError('Sample tasks are not enabled on this ELN (weighing_tasks).')
    if res.status_code in (400, 422):
        raise ValueError(f'{what}: {res.text}')
    if res.status_code not in (200, 201):
        raise request_error(res, what)


def sample_tasks(session: Connection, status: str = 'open') -> list[SampleTask]:
    """Your sample tasks with ``status`` (``'open'``, ``'with_missing_scan_results'`` or ``'done'``), newest first."""
    if status not in STATUSES:
        raise ValueError(f'status is one of {", ".join(STATUSES)}.')
    res = session.get('/api/v1/sample_tasks', params={'status': status})
    _raise(res, 'loading sample tasks')
    return [SampleTask.from_json(t, session) for t in res.json() or []]


def create_sample_task(session: Connection, sample=None, description: str | None = None,
                       required_scan_results: int = 1) -> SampleTask:
    """Create a weighing task, for a sample or (to assign later) for none (``POST /sample_tasks``)."""
    body: dict[str, Any] = {'required_scan_results': required_scan_results}
    if description is not None:
        body['description'] = description
    if sample is not None:
        body['sample_id'] = sample if isinstance(sample, int) else sample.id
    res = session.post('/api/v1/sample_tasks', data=body)
    _raise(res, 'creating a sample task')
    return SampleTask.from_json(res.json(), session)
