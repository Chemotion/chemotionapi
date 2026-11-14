"""SciFinder-n: your stored credential and the structure search through it (M7.7).

The credential is obtained in the browser (*Account & Profile > SciFinder-n*, an OAuth sign-in);
the ELN then keeps it and searches SciFinder-n on your behalf. ``/api/v1/users/scifinder``,
``/api/v1/molecules/sf``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from chemotion_api.connection import Connection, request_error

#: Structure formats the search takes.
STRUCTURE_TYPES = {'molfile': 'x-mdl-molfile', 'rxnfile': 'x-mdl-rxnfile', 'cdxml': 'x-cdxml'}


@dataclass
class ScifinderCredential:
    """Your stored SciFinder-n credential. The tokens are kept out of ``repr``."""
    id: int | None
    expires_at: str | None
    updated_at: str | None
    access_token: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)

    @property
    def present(self) -> bool:
        return bool(self.access_token)


def load_credential(session: Connection) -> ScifinderCredential | None:
    """Your SciFinder-n credential, or ``None`` (``GET /api/v1/users/scifinder``)."""
    res = session.get('/api/v1/users/scifinder')
    if res.status_code != 200:
        raise request_error(res, 'loading your SciFinder-n credential')
    data = res.json() or {}
    if not data.get('id'):
        return None
    return ScifinderCredential(data.get('id'), data.get('expires_at'), data.get('updated_at'),
                               data.get('access_token'), data.get('refresh_token'))


def search(session: Connection, structure: str, search_for: str = 'substances', structure_type: str = 'molfile') -> dict:
    """Search SciFinder-n for a structure with your stored credential (``POST /api/v1/molecules/sf``).

    :param structure: a molfile, rxnfile or CDXML.
    :param search_for: what to look for, passed to SciFinder-n as the UI's search menu does
        (e.g. ``'substances'``, ``'reactions'``, ``'suppliers'``).
    :param structure_type: ``'molfile'``, ``'rxnfile'`` or ``'cdxml'``.
    :raises PermissionError: if there is no valid credential.
    """
    if structure_type not in STRUCTURE_TYPES:
        raise ValueError(f'structure_type is one of {", ".join(STRUCTURE_TYPES)}.')
    # The ELN answers a missing or expired token with 201 and {"errors": [...]}; that is read
    # here, to raise PermissionError, rather than by the connection's generic check.
    res = session.post('/api/v1/molecules/sf', data={'str': structure, 'search': search_for,
                                                     'ctype': STRUCTURE_TYPES[structure_type]},
                       allow_error_body=True)
    if res.status_code not in (200, 201):
        raise request_error(res, 'searching SciFinder-n')
    data = res.json()
    errors = data.get('errors') if isinstance(data, dict) else None
    if errors:
        message = '; '.join(errors)
        raise (PermissionError if 'token' in message.lower() else ConnectionError)(message)
    return data
