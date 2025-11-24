import pytest
from chemotion_api import Instance


def test_all_types(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    assert list(instance.get_all_types()) == ['chemotion:type/wellplate/2.1.1',
                                               'chemotion:type/screen/2.1.1',
                                               'chemotion:type/sample/2.1.1',
                                               'chemotion:type/research_plan/2.1.1',
                                               'chemotion:type/reaction/2.1.1',
                                               'chemotion:type/device_description/2.1.1',
                                               'chemotion:type/cell_line/2.1.1',
                                               'chemotion:generic_type/wrk/2.0',
                                               'chemotion:generic_type/wrk/1.0',
                                               'chemotion:generic_type/try/1.0']


def test_instance(config_login):
    instance = Instance(config_login.get('ELN_URL'))
    assert instance.test_connection() == instance


def test_invalid_url():
    instance = Instance("https://0.0.0.0/")
    with pytest.raises(ConnectionError):
        instance.test_connection()


def test_invalid_instance():
    instance = Instance("https://www.google.de/")
    with pytest.raises(ConnectionError):
        instance.test_connection()
