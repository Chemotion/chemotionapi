"""Account security and counters: two-factor login, API tokens, short-label counters (M7.2, M7.3).

API tokens (``chemtoken_…``) are long-lived credentials for scripts; log in with one through
``Instance.login_token``. The ELN issues and revokes them only for accounts with two-factor login,
and asks for a current one-time password each time. ``/api/v1/users``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemotion_api.connection import Connection, request_error


@dataclass
class ApiToken:
    id: int
    name: str
    expires_at: str | None
    revoked: bool


class OtpRequired(PermissionError):
    """The action needs a (correct) one-time password of the account's authenticator app."""


def _otp_errors(res, what: str) -> None:
    if res.status_code == 401:
        raise PermissionError(f'{what}: the account needs two-factor login enabled first.')
    if res.status_code == 422:
        body = res.json() if res.text.startswith('{') else {}
        if body.get('otp_wrong'):
            raise OtpRequired(f'{what}: the one-time password was wrong.')
        raise OtpRequired(f'{what}: give the current one-time password (otp=...).')


def two_factor_enabled(session: Connection) -> bool:
    """Whether the account logs in with a one-time password (``GET /api/v1/users/two_factor``)."""
    res = session.get('/api/v1/users/two_factor')
    if res.status_code != 200:
        raise request_error(res, 'reading the two-factor setting')
    return bool(res.json().get('otp_required_for_login'))


def request_two_factor_change(session: Connection) -> None:
    """Ask for two-factor login to be switched on — or off, if it is on (``PUT /api/v1/users/two_factor``).
    The ELN emails the account a confirmation link; nothing changes until it is followed."""
    res = session.put('/api/v1/users/two_factor')
    if res.status_code not in (200, 201):
        raise request_error(res, 'requesting a two-factor change')


def api_tokens(session: Connection) -> list[ApiToken]:
    """Your API tokens that have not expired (from ``GET /api/v1/users/current``)."""
    res = session.get('/api/v1/users/current')
    if res.status_code != 200:
        raise request_error(res, 'loading your API tokens')
    return [ApiToken(t['id'], t.get('name') or '', t.get('expires_at'), bool(t.get('revoked')))
            for t in (res.json().get('user') or {}).get('tokens') or []]


def create_api_token(session: Connection, otp: str, name: str | None = None, expires_in_days: int = 30) -> str:
    """Create an API token (``POST /api/v1/users/auth_token``).

    :param otp: the current one-time password of your authenticator app.
    :param expires_in_days: 1 to 600.
    :return: the token itself; the ELN shows it only this once.
    :raises PermissionError: if the account has no two-factor login.
    :raises OtpRequired: if the one-time password is missing or wrong.
    """
    if not 1 <= expires_in_days <= 600:
        raise ValueError('expires_in_days is 1 to 600.')
    body: dict[str, Any] = {'otp_attempt': otp, 'expires_in_days': expires_in_days}
    if name:
        body['name'] = name
    res = session.post('/api/v1/users/auth_token', data=body)
    _otp_errors(res, 'Creating an API token')
    if res.status_code not in (200, 201):
        raise request_error(res, 'creating an API token')
    return res.json()['token']


def revoke_api_token(session: Connection, token: ApiToken | int, otp: str) -> None:
    """Revoke an API token (``POST /api/v1/users/revoke_auth_token``).

    :raises LookupError: if it is not one of yours, or already revoked.
    """
    token_id = token if isinstance(token, int) else token.id
    res = session.post('/api/v1/users/revoke_auth_token', data={'id': token_id, 'otp_attempt': otp})
    _otp_errors(res, 'Revoking an API token')
    if res.status_code in (404, 409):
        raise LookupError(f'API token {token_id}: {res.text}')
    if res.status_code not in (200, 201, 204):
        raise request_error(res, f'revoking API token {token_id}')


def set_counter(session: Connection, element_type: str, value: int) -> dict:
    """Set the counter behind your next short label of an element type, e.g. ``'samples'``,
    ``'reactions'``, ``'wellplates'`` or a generic element's name (``PUT /api/v1/users/update_counter``).

    The next element gets ``value + 1``. Labels are not checked for clashes, so going backwards
    can repeat existing labels.
    """
    if value < 0:
        raise ValueError('A counter is 0 or more.')
    res = session.put('/api/v1/users/update_counter', data={'type': element_type, 'counter': value})
    if res.status_code not in (200, 201):
        raise request_error(res, f'setting the {element_type} counter')
    return res.json()


def set_reaction_label(session: Connection, prefix: str, count: int) -> None:
    """Set the prefix and the counter of your reaction short labels (``<initials>-<prefix><n>``)
    (``PUT /api/v1/users/reaction_short_label``)."""
    if count < 0:
        raise ValueError('A counter is 0 or more.')
    res = session.put('/api/v1/users/reaction_short_label', data={'reactions_count': count, 'reaction_name_prefix': prefix})
    if res.status_code not in (200, 201, 204):
        raise request_error(res, 'setting the reaction short label')
