import pytest
from chemotion_api import Instance


def test_all_types(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    assert list(instance.get_all_types()) == ['chmotion:type/wellplate/1.10.2',
                                              'chmotion:type/screen/1.10.2',
                                              'chmotion:type/sample/1.10.2',
                                              'chmotion:type/research_plan/1.10.2',
                                              'chmotion:type/reaction/1.10.2',
                                              'chmotion:type/cell_line/1.10.2',
                                              'chmotion:generic_type/wrk/2.0',
                                              'chmotion:generic_type/wrk/1.0',
                                              'chmotion:generic_type/try/1.0']


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