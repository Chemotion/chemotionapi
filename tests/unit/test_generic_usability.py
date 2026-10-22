from types import SimpleNamespace

import pytest

from chemotion_api.elements.abstract_element import Analyses
from chemotion_api.elements.attachments import Attachment
from chemotion_api import labImotion
from chemotion_api.labImotion import GenericManager, GenericElementKlass


def _klass(id, name, label, version):
    return SimpleNamespace(id=id, name=name, label=label, version=version, is_active=True)


@pytest.fixture
def manager(monkeypatch):
    klasses = [_klass(1, 'wrk', 'Workflow', '1.0'), _klass(2, 'wrk', 'Workflow', '2.0'),
               _klass(3, 'plan', 'Plan', '1.0')]
    monkeypatch.setattr(GenericElementKlass, 'load_all', classmethod(lambda cls, con: klasses))
    return GenericManager(None)


def test_template_class_alias():
    assert labImotion.GenericElement is GenericElementKlass


def test_get_element_by_name_label_and_version(manager):
    assert manager.get_element('plan').id == 3
    assert manager.get_element('wrk', version='2.0').id == 2
    assert manager.get_element(label='Workflow', version='1.0').id == 1
    assert manager.get_element(id=3).name == 'plan'


def test_get_element_errors_list_candidates(manager):
    with pytest.raises(KeyError, match=r"Multiple results.*Workflow \(name=wrk, version=1.0, id=1\).*version=2.0"):
        manager.get_element('wrk')
    with pytest.raises(KeyError, match=r"No element found.*Available: .*Plan"):
        manager.get_element('xyz')


def test_analyses_attribute_access():
    ana = Analyses({'id': 7, 'name': 'QA check', 'description': '', 'extended_metadata': {'kind': 'NMR'},
                    'children': []}, None)
    assert ana.name == 'QA check' and ana.kind == 'NMR' and ana.id == 7 and ana.datasets == []
    ana.name = 'Renamed'
    assert ana['name'] == 'Renamed'
    with pytest.raises(AttributeError):
        ana.unknown


def test_attachment_attribute_access():
    att = Attachment(None, {'id': 3, 'filename': 'a.txt'})
    assert att.filename == 'a.txt' and att.id == 3
    att.filename = 'b.txt'
    assert att['filename'] == 'b.txt'
    with pytest.raises(AttributeError):
        att.unknown
