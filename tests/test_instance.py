import pytest
from chemotion_api import Instance


def test_all_types(instance_with_collection):
    instance: Instance = instance_with_collection['instance']
    types = set(instance.get_all_types())
    # Core type IRIs carry the server version; derive it instead of hard-coding a release.
    version = next(t for t in types if t.startswith('chemotion:type/sample/')).rsplit('/', 1)[1]
    expected_core = {f'chemotion:type/{name}/{version}' for name in
                     ['wellplate', 'screen', 'sample', 'research_plan', 'reaction',
                      'device_description', 'cell_line']}
    assert expected_core <= types
    # Generic klasses from the seeded database.
    assert {'chemotion:generic_type/wrk/2.0', 'chemotion:generic_type/wrk/1.0',
            'chemotion:generic_type/try/1.0'} <= types


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
