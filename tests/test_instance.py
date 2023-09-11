import pytest
from  requests.exceptions import ConnectionError
from chemotion_api import Instance

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