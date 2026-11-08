"""MTT (dose-response) assay requests of generic elements (M6.5).

An MTT request hands the wells of some wellplates to the external MTT analysis app: the ELN creates
the request with a token link, the app downloads the plate data, fits dose-response curves and
uploads its *outputs* back to the request. ``/api/v1/mtt``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: Request states (``DoseRespRequest::STATE_*``).
STATES = {-1: 'error', 0: 'initial', 1: 'processing', 2: 'completed'}


@dataclass
class MttOutput:
    id: int
    output_data: Any
    notes: str | None = None
    created_at: str | None = None


@dataclass
class MttRequest:
    id: int
    element_id: int
    state: int
    state_name: str
    request_id: str | None = None
    active: bool = False
    revoked: bool = False
    expired: bool = False
    resp_message: str | None = None
    outputs: list[MttOutput] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _session: Connection | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: dict[str, Any], session: Connection | None = None) -> MttRequest:
        state = int(data.get('state') or 0)
        return cls(id=data['id'], element_id=int(data.get('element_id') or 0), state=state,
                   state_name=data.get('state_name') or STATES.get(state, 'unknown'),
                   request_id=data.get('request_id'), active=bool(data.get('active')),
                   revoked=bool(data.get('revoked')), expired=bool(data.get('expired')),
                   resp_message=data.get('resp_message'),
                   outputs=[MttOutput(o['id'], o.get('output_data'), o.get('notes'), o.get('created_at'))
                            for o in data.get('outputs') or []], raw=data, _session=session)

    def _con(self) -> Connection:
        if self._session is None:
            raise ValueError('Not attached to a server connection.')
        return self._session

    def update(self, state: int | None = None, message: str | None = None, revoked: bool | None = None,
               wellplates_metadata: dict | None = None, input_metadata: dict | None = None) -> MttRequest:
        """Change the request (``PATCH /api/v1/mtt/requests/:id``).

        :param state: one of :data:`STATES`.
        :param revoked: True revokes the app's access token, False restores it.
        """
        if state is not None and state not in STATES:
            raise ValueError(f'state is one of {STATES}.')
        body: dict[str, Any] = {k: v for k, v in (('state', state), ('resp_message', message), ('revoked', revoked),
                                                   ('wellplates_metadata', wellplates_metadata),
                                                   ('input_metadata', input_metadata)) if v is not None}
        res = self._con().patch(f'/api/v1/mtt/requests/{self.id}', data=body)
        _raise(res, f'updating MTT request {self.id}')
        answer = res.json().get('request') or {}
        self.state = answer.get('state', self.state)
        self.state_name = answer.get('state_name', self.state_name)
        self.resp_message = answer.get('resp_message', self.resp_message)
        self.revoked = bool(answer.get('revoked', self.revoked))
        return self

    def revoke(self) -> MttRequest:
        """Revoke the external app's access to this request."""
        return self.update(revoked=True)

    def delete(self) -> None:
        delete_requests(self._con(), [self])


def _raise(res, what: str) -> None:
    if res.status_code == 404:
        raise LookupError(f'{what}: not found, or not yours.')
    if res.status_code == 403:
        raise PermissionError(f'{what}: you may not edit the element.')
    if res.status_code == 422:
        raise ValueError(f'{what}: {res.text}')
    if res.status_code not in (200, 201):
        raise request_error(res, what)


def create_request(session: Connection, element, wellplates) -> str:
    """Start an MTT assay of ``wellplates`` for a generic element
    (``POST /api/v1/mtt/create_mtt_request``).

    :return: the link that opens the external MTT app on this request.
    """
    ids = [w if isinstance(w, int) else w.id for w in wellplates]
    if not ids or any(i is None for i in ids):
        raise ValueError('Give the saved wellplates to analyse.')
    res = session.post('/api/v1/mtt/create_mtt_request', data={'id': element.id, 'wellplate_ids': ids})
    _raise(res, f'creating an MTT request for element {element.id}')
    answer = res.json()
    return answer if isinstance(answer, str) else json.dumps(answer)


def list_requests(session: Connection, element) -> list[MttRequest]:
    """Your MTT requests of an element, newest first, with their outputs (``GET /api/v1/mtt/requests``)."""
    res = session.get('/api/v1/mtt/requests', params={'element_id': element.id})
    _raise(res, f'loading the MTT requests of element {element.id}')
    return [MttRequest.from_json(r, session) for r in res.json() or []]


def _delete_many(session: Connection, url: str, items, what: str) -> int:
    ids = [i if isinstance(i, int) else i.id for i in items]
    if not ids:
        raise ValueError(f'No {what} given.')
    res = session.delete(url, data=json.dumps({'ids': ids}), headers=session.get_json_session_header())
    _raise(res, f'deleting {what}')
    return int(res.json().get('deleted_count') or 0)


def delete_requests(session: Connection, requests) -> int:
    """Delete MTT requests of yours (``DELETE /api/v1/mtt/requests``). :return: how many were deleted."""
    return _delete_many(session, '/api/v1/mtt/requests', requests, 'MTT requests')


def delete_outputs(session: Connection, outputs) -> int:
    """Delete MTT outputs of your requests (``DELETE /api/v1/mtt/outputs``)."""
    return _delete_many(session, '/api/v1/mtt/outputs', outputs, 'MTT outputs')


def delete_output_result(session: Connection, output, sample_name: str) -> dict:
    """Remove one sample's result from an output (``DELETE /api/v1/mtt/outputs/:id/results``).
    An output left empty is deleted. :return: the server's answer (``output_deleted``, ``output``)."""
    output_id = output if isinstance(output, int) else output.id
    res = session.delete(f'/api/v1/mtt/outputs/{output_id}/results', params={'sample_name': sample_name})
    _raise(res, f'removing {sample_name!r} from MTT output {output_id}')
    return res.json()
