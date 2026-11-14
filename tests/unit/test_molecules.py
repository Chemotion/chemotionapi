"""Molecules, completed (M2.1), offline: request shapes and the server's quiet failures."""
import pytest

from chemotion_api.elements.sample import MoleculeManager

ETHANOL = {'id': 7, 'inchikey': 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N', 'cano_smiles': 'CCO', 'sum_formular': 'C2H6O',
           'molfile': 'M  END', 'cas': ['64-17-5'], 'molecule_svg_file': 'abc.svg'}
DUMMY = dict(ETHANOL, id=12, inchikey='DUMMY', cano_smiles=None, molfile=None, cas=[])


class _Res:
    def __init__(self, status, payload=None, content=b''):
        self.status_code, self._payload, self.text, self.content = status, payload, str(payload), content

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res):
        self.res, self.calls = res, []

    def get(self, url, **kw):
        self.calls.append(('get', url, kw.get('params')))
        return self.res

    def post(self, url, **kw):
        self.calls.append(('post', url, kw.get('data')))
        return self.res


def test_molfile_creates_via_the_molecules_route():
    session = _Session(_Res(201, ETHANOL))
    mol = MoleculeManager(session).create_molecule_by_molfile('M  END')
    assert mol.id == 7
    assert session.calls == [('post', '/api/v1/molecules', {'molfile': 'M  END', 'decoupled': False})]


def test_an_unreadable_molfile_is_an_error_not_the_placeholder_molecule():
    with pytest.raises(ValueError, match='placeholder'):
        MoleculeManager(_Session(_Res(201, DUMMY))).create_molecule_by_molfile('garbage')


def test_decoupled_samples_get_the_placeholder_on_purpose():
    assert MoleculeManager(_Session(_Res(201, DUMMY))).create_molecule_by_molfile('x', decoupled=True)['inchikey'] == 'DUMMY'


@pytest.mark.parametrize('molfile', ['', '   \n'])
def test_an_empty_molfile_sends_nothing(molfile):
    session = _Session(None)
    with pytest.raises(ValueError, match='empty'):
        MoleculeManager(session).create_molecule_by_molfile(molfile)
    assert session.calls == []


def test_a_render_failure_is_a_value_error():
    with pytest.raises(ValueError, match='render'):
        MoleculeManager(_Session(_Res(422, {'error': 'Failed to generate SVG'}))).create_molecule_by_molfile('M  END')


@pytest.mark.parametrize('payload, expected', [({'molecule': ETHANOL}, 7), ({'molecule': None}, None), ({}, None)])
def test_lookup_by_inchikey(payload, expected):
    mol = MoleculeManager(_Session(_Res(201, payload))).get_molecule_by_inchikey('X')
    assert (mol.id if mol else None) == expected


@pytest.mark.parametrize('payload, expected', [(ETHANOL, ['64-17-5']), (None, []), ({'cas': [None, '']}, [])])
def test_cas_numbers(payload, expected):
    assert MoleculeManager(_Session(_Res(200, payload))).load_cas('X') == expected


def test_render_svg_failure_is_reported():
    with pytest.raises(ValueError, match='All rendering services failed'):
        MoleculeManager(_Session(_Res(201, {'success': False, 'error': 'All rendering services failed'}))).render_svg('M')


@pytest.mark.parametrize('ref, url', [('abc.svg', '/images/molecules/abc.svg'),
                                      ('/images/molecules/abc.svg', '/images/molecules/abc.svg')])
def test_load_svg_by_name_or_path(ref, url):
    session = _Session(_Res(200, None, b'<svg/>'))
    assert MoleculeManager(session).load_svg(ref) == b'<svg/>'
    assert session.calls[0][1] == url


def test_molecular_weight():
    assert MoleculeManager(_Session(_Res(200, 46.06848))).molecular_weight('C2H6O') == pytest.approx(46.068, abs=1e-3)
