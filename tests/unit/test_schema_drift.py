"""Offline tests for GenericManager.check_schema_drift (bundled schemas vs served klasses)."""
import copy
import json
import os

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fixtures')


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class _FakeConnection:
    """Serves one klass fixture per listing endpoint, like a live instance would."""

    def __init__(self, by_url):
        self._by_url = by_url

    def get(self, url, **kwargs):
        return _FakeResponse({'klass': self._by_url.get(url, [])})


def _load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def _manager(element=None, segment=None, dataset=None):
    from chemotion_api.labImotion import (GenericManager, GenericElement, GenericSegment,
                                          GenericDataset)
    con = _FakeConnection({
        GenericElement.url: element or [],
        GenericSegment.url: segment or [],
        GenericDataset.url: dataset or [],
    })
    return GenericManager(con)


def test_conforming_klasses_report_no_drift():
    gm = _manager(element=[_load('GenericElement.json')],
                  segment=[_load('GenericSegment.json')],
                  dataset=[_load('GenericDataset.json')])
    report = gm.check_schema_drift()
    assert set(report) == {'element', 'segment', 'dataset'}
    assert all(issues == [] for issues in report.values()), report


def test_drifted_klass_is_reported_with_messages():
    broken = copy.deepcopy(_load('GenericElement.json'))
    del broken['properties_template']          # required by the bundled element schema
    broken['label'] = 12345                    # wrong type
    gm = _manager(element=[broken])
    report = gm.check_schema_drift()
    assert len(report['element']) == 1
    entry = report['element'][0]
    assert entry['name'] == broken.get('name')
    assert entry['errors']                     # human-readable jsonschema messages
    assert report['segment'] == [] and report['dataset'] == []


def test_empty_instance_reports_no_drift():
    report = _manager().check_schema_drift()
    assert all(issues == [] for issues in report.values())
