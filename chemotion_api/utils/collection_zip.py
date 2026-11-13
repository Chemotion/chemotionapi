"""The server's own collection export and import (Chemotion's native ZIP format, not ``.eln``).

Both report through the user's notifications rather than in the HTTP response: export is a
background job that posts a "Collection Import and Export" message carrying a download link when
the archive is ready, and import posts a message (or a "… Failure" one) when it has finished.
Messages are only read here, never acknowledged, so they still appear in the ELN's UI.
"""
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from chemotion_api.connection import Connection, request_error

SUBJECT_OK = 'Collection Import and Export'
SUBJECT_FAIL = 'Collection Import and Export Failure'
_ZIP_PATH = re.compile(r'/zip/[\w-]+\.zip')


def message_ids(session: Connection) -> set:
    return {str(m.get('id')) for m in _messages(session)}


def _messages(session: Connection) -> list[dict]:
    res = session.get('/api/v1/messages/list', params={'is_ack': 9})
    if res.status_code != 200:
        raise request_error(res, 'reading notifications')
    return (res.json() or {}).get('messages') or []


def new_messages(session: Connection, seen: set) -> list[dict]:
    return [m for m in _messages(session) if str(m.get('id')) not in seen
            and m.get('subject') in (SUBJECT_OK, SUBJECT_FAIL)]


def _text(message: dict) -> str:
    content = message.get('content') or {}
    return str(content.get('data') or '') if isinstance(content, dict) else str(content)


def export_collection_zip(session: Connection, collection_id: int, label: str, destination,
                          timeout: float = 900, poll_interval: float = 2.0) -> Path:
    """Ask the server to export one collection and save the archive to ``destination``.

    :raises PermissionError: if you may not export it — your own collections always, a shared one
        only with full detail access (401).
    :raises ConnectionError: if the server reports the export failed or links somewhere unexpected.
    :raises TimeoutError: if no archive is announced within ``timeout`` seconds.
    """
    seen = message_ids(session)
    res = session.post('/api/v1/collections/export', data={'collection_ids': [collection_id]})
    if res.status_code == 401:
        raise PermissionError(
            f'You may not export collection {collection_id}: a collection shared with you needs '
            f'full detail access to be exported.')
    if res.status_code not in (200, 201, 204):
        raise request_error(res, f'exporting collection {collection_id}')

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for message in new_messages(session, seen):
            text = _text(message)
            if 'Export' not in text or label not in text:
                continue
            if message.get('subject') == SUBJECT_FAIL:
                raise ConnectionError(f'The server could not export collection {collection_id}: {text}')
            content = message.get('content') or {}
            # The link's host is the server's configured root URL, which need not be the address
            # we connect to; only the path is used, and only the shape the export job produces.
            path = urlsplit(str(content.get('url') or '')).path
            if not _ZIP_PATH.fullmatch(path):
                raise ConnectionError(f'Unexpected export download link: {content.get("url")!r}')
            return _download(session, path, Path(destination))
        time.sleep(poll_interval)
    raise TimeoutError(f'No export archive for collection {collection_id} within {timeout:.0f} s.')


def _download(session: Connection, path: str, destination: Path) -> Path:
    res = session.get(path, stream=True)
    if res.status_code != 200:
        raise request_error(res, f'downloading {path}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, part = tempfile.mkstemp(dir=destination.parent, suffix='.part')
    try:
        with os.fdopen(fd, 'wb') as out:
            for chunk in res.iter_content(1024 * 1024):
                out.write(chunk)
        os.replace(part, destination)
    except BaseException:
        Path(part).unlink(missing_ok=True)
        raise
    return destination


def import_collection_zip(session: Connection, path) -> None:
    """Upload a collection archive; the server imports it before answering.

    :raises PermissionError: on 401.
    :raises ValueError: if the server reports the import failed.
    """
    seen = message_ids(session)
    path = Path(path)
    with path.open('rb') as fh:
        res = session.post('/api/v1/collections/import',
                           files={'file': (path.name, fh, 'application/zip')})
    if res.status_code == 401:
        raise PermissionError('You may not import collections.')
    if res.status_code == 413:
        raise ValueError(f'{path.name} is larger than the server accepts.')
    if res.status_code not in (200, 201, 204):
        raise request_error(res, f'importing {path.name}')
    for message in new_messages(session, seen):
        if message.get('subject') == SUBJECT_FAIL and 'import' in _text(message).lower():
            raise ValueError(f'The server could not import {path.name}: {_text(message)}')
