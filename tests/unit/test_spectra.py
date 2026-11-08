"""Spectra processing (M5.1), offline: request shapes and decoded answers."""
import base64

import pytest

from chemotion_api.spectra import Spectra


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    host_url = 'http://127.0.0.1:3579'

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append(('get', url, kw.get('params')))
        return self.responses.pop(0)

    def post(self, url, data=None, files=None, **kw):
        self.calls.append(('post', url, data, sorted(files or {})))
        return self.responses.pop(0)


def _b64(data: bytes) -> str:
    return base64.encodebytes(data).decode()


def test_save_and_infer_decode_the_files():
    jcamp = {'id': 9, 'aasm_state': 'edited', 'file': _b64(b'##TITLE=x'), 'predictions': {}}
    session = _Session(_Res(201, {'files': [jcamp]}), _Res(201, {'files': [jcamp], 'predict': {'ok': True}}))
    sp = Spectra(session)
    saved = sp.save({'id': 5}, peaks_str='7.26,100', shift_ref_name='CDCl3')
    assert (saved.id, saved.content, saved.state) == (9, b'##TITLE=x', 'edited')
    assert session.calls[0][2] == {'attachment_id': 5, 'peaks_str': '7.26,100', 'shift_ref_name': 'CDCl3'}
    _, predict = sp.infer(5)
    assert predict == {'ok': True} and session.calls[1][1] == '/api/v1/attachments/infer'
    with pytest.raises(ValueError, match='Unknown spectrum parameters'):
        sp.save(5, colour='red')


def test_failures_map_to_errors():
    with pytest.raises(ValueError, match='could not be generated'):
        Spectra(_Session(_Res(422, {}))).save(5)
    with pytest.raises(PermissionError):
        Spectra(_Session(_Res(401, {}))).save(5)
    with pytest.raises(LookupError):
        Spectra(_Session(_Res(422, {'code': 'page_not_found'}))).lcms_page(5, 1.5)
    with pytest.raises(ValueError, match='front one'):
        Spectra(_Session()).combine([5], front_index=3)


def test_regenerate_combine_convert(tmp_path):
    raw = tmp_path / 'ir.dx'
    raw.write_text('data')
    session = _Session(_Res(201, {}), _Res(201, {'status': True}),
                       _Res(201, {'status': True, 'jcamp': _b64(b'J'), 'img': _b64(b'P')}), _Res(201, {'status': False}))
    sp = Spectra(session)
    sp.regenerate([{'id': 1}], generated=[2])
    sp.combine([1, 2], front_index=1)
    assert sp.convert(str(raw), mass=46.07) == (b'J', b'P')
    with pytest.raises(ValueError, match='could not convert'):
        sp.convert(str(raw))
    assert session.calls[0][2] == {'original': [1], 'generated': [2]}
    assert session.calls[1][2] == {'spectra_ids': [1, 2], 'front_spectra_idx': 1}
    assert session.calls[2][2:] == ({'mass': '46.07'}, ['file'])


def test_lcms_page_and_nmrium():
    session = _Session(_Res(201, {'file': {'id': 4, 'file': _b64(b'##PAGE'), 'polarity': 'positive'}}),
                       _Res(200, {'nmrium_url': 'https://nmrium.example'}))
    page = Spectra(session).lcms_page(3, 1.5, 'positive')
    assert page == {'id': 4, 'content': b'##PAGE', 'polarity': 'positive'}
    assert session.calls[0][2] == {'attachment_id': 3, 'retention_time': '1.5', 'polarity': 'positive'}
    assert Spectra(session).nmrium_url() == 'https://nmrium.example'
    assert session.calls[1][1] == '/api/v1/chemspectra/nmrium_wrapper/eln'
