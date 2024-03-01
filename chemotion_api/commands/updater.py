import yaml

def read_docker_compose(file_path: str) -> dict[str:dict|str]:
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)


def write_docker_compose(file_path: str, content: dict[str:dict|str]):
    with open(file_path, 'w') as file:
        yaml.dump(content, file, default_flow_style=False, sort_keys=False)


def update_images(file_path: str, **kwargs):
    content = read_docker_compose(file_path)

    for service, image in kwargs.items():
        if service in content['services']:
            content['services'][service]['image'] = image

    write_docker_compose(file_path, content)


def update_eln_port(file_path: str, eln_port: int):
    content = read_docker_compose(file_path)
    content['services']['eln']['ports'] = [f'{eln_port}:4000']
    write_docker_compose(file_path, content)


def update_db_port(file_path: str, postgresql_port: int):
    content = read_docker_compose(file_path)
    content['services']['db']['ports'] = [f'{postgresql_port}:5432']
    write_docker_compose(file_path, content)


def get_eln_port(file_path: str):
    content = read_docker_compose(file_path)
    return int(content['services']['eln']['ports'][0].split(':')[0])


def get_db_port(file_path: str):
    content = read_docker_compose(file_path)
    return int(content['services']['db']['ports'][0].split(':')[0])