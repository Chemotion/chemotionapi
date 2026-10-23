import json
import logging
import os
from threading import Thread

from psutil import process_iter, AccessDenied
from signal import SIGTERM  # or SIGKILL
import subprocess
import uuid
from random import random

from chemotion_api import Instance
import pytest

DEFAULT_CONFIG = {
    "ELN_URL": "http://127.0.0.1:3000",
    "ELN_USER": "",
    "ELN_PASS": "",
    "ELN_ADMIN_USER": "",
    "ELN_ADMIN_PASS": "",
    "PG_PASSWORD": "postgres",
    "PG_HOST": "localhost",
    "PG_PORT": "54320",
    "PG_USER": "postgres",
    "PG_DB": "chemotion",
    "ELN_PORT": "3579",
    "DOCKER_FILE": "docker-compose.yml",
    "DOCKER_CWD": "../../test_config",
    "DOCKER_COMPOSE_SERVICE": "eln",
    "WAIT_FOR_MANUAL_RESTART": "0",
    "NO_SETUP": "0"
}

CONFIG = {}
CHEMOTION_PROCESS: subprocess.Popen | None = None


def set_config():
    global CONFIG, DEFAULT_CONFIG

    # config.json is local (gitignored); without it the defaults and environment variables are used
    file = os.path.join(os.path.dirname(__file__), "config.json")
    data = {}
    if os.path.isfile(file):
        with open(file, "r") as jsonfile:
            data = json.load(jsonfile)

    for key, val in DEFAULT_CONFIG.items():
        CONFIG[key] = str(os.getenv(key, data.get(key, val)))


# task for worker threads
def write_proces_logs():
    global CHEMOTION_PROCESS
    # task loop
    with open('logs.txt', 'w+') as f:
        while True:
            line = CHEMOTION_PROCESS.stdout.readline().decode("utf-8")
            if not line:
                break

            f.write(line.strip() + '\n')


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs the test ELN (all tests outside tests/unit)")


def pytest_collection_modifyitems(config, items):
    # Everything outside tests/unit talks to the test ELN
    unit_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unit')
    for item in items:
        if os.path.commonpath([str(item.path), unit_dir]) != unit_dir:
            item.add_marker(pytest.mark.integration)


def pytest_sessionstart(session):
    global DEFAULT_CONFIG, CONFIG, CHEMOTION_PROCESS
    set_config()
    if CONFIG.get('NO_SETUP') != '1':
        path = os.path.join(os.getcwd(), 'data/setup_chemotion_db.sh')
        path_dir = os.path.join(os.getcwd(), 'data')

        CHEMOTION_PROCESS = subprocess.Popen(path, shell=True, executable='/bin/bash', cwd=path_dir,
                                             env=dict(os.environ, **CONFIG),
                                             stdin=subprocess.DEVNULL,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT)

        while True:
            line = CHEMOTION_PROCESS.stdout.readline().decode("utf-8")
            if not line:
                raise Exception(f'{path} did not start Server')

            print(line.strip())
            if "**SUCCESS**" in line:
                Thread(target=write_proces_logs, args=()).start()
                break

        if CONFIG["WAIT_FOR_MANUAL_RESTART"] != '0':
            print("Waiting for manual restart of the Chemotion Server...")
            input("Press Enter to continue...")

    logging.info('Config:\n' + '\n'.join(["#\t%s=%s" % (key, val) for key, val in CONFIG.items()]))


def pytest_sessionfinish(session, exitstatus):
    """
    Called after whole test run finished, right before
    returning the exit status to the system.
    """
    global CHEMOTION_PROCESS
    if CHEMOTION_PROCESS is not None:
        for proc in process_iter():
            try:
                for conns in proc.net_connections(kind='inet'):
                    if conns.laddr.port == 3579:
                        proc.send_signal(SIGTERM)  # or SIGKILL
            except AccessDenied:
                pass

    pass


@pytest.fixture(scope='session')
def delete_col_prefix():
    return "API_TEST_"


@pytest.fixture(scope='session')
def config_login():
    return CONFIG


@pytest.fixture(scope='session')
def logged_in_instance(delete_col_prefix):
    instance = Instance(CONFIG['ELN_URL']).test_connection().login(CONFIG['ELN_USER'], CONFIG['ELN_PASS'])
    yield instance


@pytest.fixture()
def instance_with_collection(logged_in_instance, delete_col_prefix):
    name = delete_col_prefix + uuid.uuid4().__str__()
    root_col = logged_in_instance.get_root_collection()
    root_col.add_collection(name)
    root_col.save()
    main_collection = root_col.get_collection(name)
    yield {
        'instance': logged_in_instance,
        'main_collection': main_collection,
        'name': name
    }


@pytest.fixture()
def instance_with_test_samples(instance_with_collection):
    main_collection = instance_with_collection['main_collection']
    sample_ids = []
    for smiles in ['B', 'N', 'C', 'CC', 'CN']:
        s = main_collection.new_sample_smiles(smiles)
        s.properties['target_amount']['value'] = random()
        s.save()
        sample_ids.append(s.id)

    yield instance_with_collection | {
        'sample_ids': sample_ids

    }
