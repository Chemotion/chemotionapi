"""Read and rewrite fields of a ``docker-compose.yml`` for a Chemotion instance.

Helpers used by :class:`chemotion_api.commands.InstanceManager` to update service images and
host ports while preserving the rest of the compose file.
"""
from typing import Any

import yaml

def read_docker_compose(file_path: str) -> dict[str, Any]:
    """Parse a ``docker-compose.yml`` file into a dict.

    :param file_path: path to the compose file.
    :return: the parsed compose document.
    """
    with open(file_path) as file:
        return yaml.safe_load(file)


def write_docker_compose(file_path: str, content: dict[str, Any]) -> None:
    """Write a compose document back to disk in block style, preserving key order.

    :param file_path: path to the compose file to overwrite.
    :param content: the compose document to serialize.
    """
    with open(file_path, 'w') as file:
        yaml.dump(content, file, default_flow_style=False, sort_keys=False)


def update_images(file_path: str, **kwargs):
    """Set the ``image`` of each named service present in the compose file.

    :param file_path: path to the compose file.
    :param kwargs: ``service_name=image_reference`` pairs; unknown services are ignored.
    """
    content = read_docker_compose(file_path)

    for service, image in kwargs.items():
        if service in content['services']:
            content['services'][service]['image'] = image

    write_docker_compose(file_path, content)


def update_eln_port(file_path: str, eln_port: int):
    """Set the host port mapped to the ELN service's container port 4000.

    :param file_path: path to the compose file.
    :param eln_port: new host port for the ELN service.
    """
    content = read_docker_compose(file_path)
    content['services']['eln']['ports'] = [f'{eln_port}:4000']
    write_docker_compose(file_path, content)


def update_db_port(file_path: str, postgresql_port: int):
    """Set the host port mapped to the database service's container port 5432.

    :param file_path: path to the compose file.
    :param postgresql_port: new host port for the database service.
    """
    content = read_docker_compose(file_path)
    content['services']['db']['ports'] = [f'{postgresql_port}:5432']
    write_docker_compose(file_path, content)


def get_eln_port(file_path: str):
    """Return the host port mapped to the ELN service, read from the compose file.

    :param file_path: path to the compose file.
    :return: the ELN host port as an ``int``.
    """
    content = read_docker_compose(file_path)
    ports = content['services']['eln'].get('ports', [])
    if not ports:
        raise ValueError("ELN service has no ports configured in the compose file")
    return int(ports[0].split(':')[0])


def get_db_port(file_path: str):
    """Return the host port mapped to the database service, read from the compose file.

    :param file_path: path to the compose file.
    :return: the database host port as an ``int``.
    """
    content = read_docker_compose(file_path)
    ports = content['services']['db'].get('ports', [])
    if not ports:
        raise ValueError("Database service has no ports configured in the compose file")
    return int(ports[0].split(':')[0])