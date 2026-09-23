import pytest
from chemotion_api import Instance


def test_all_types(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    assert list(instance.get_all_types()) == ['chemotion:type/wellplate/3.1.2',
                                               'chemotion:type/sequence_based_macromolecule_sample/3.1.2',
                                               'chemotion:type/screen/3.1.2',
                                               'chemotion:type/sample/3.1.2',
                                               'chemotion:type/research_plan/3.1.2',
                                               'chemotion:type/reaction/3.1.2',
                                               'chemotion:type/device_description/3.1.2',
                                               'chemotion:type/cell_line/3.1.2',
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
