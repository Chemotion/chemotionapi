import json
import logging
import os
from threading import Thread

from psutil import process_iter, AccessDenied
from signal import SIGTERM  # or SIGKILL
import subprocess
import uuid
from random import random

import pytest
# NOTE: chemotion_api is imported lazily inside fixtures (not at module level) so collecting
# pure-logic unit tests does not pull in the heavy rdflib/linkml/chem_dcat_ap stack. This keeps
# the offline unit suite's memory footprint small.

DEFAULT_CONFIG = {
    # Defaults match the seeded docker stack in test_config/ (eln published on 3579) and the
    # fictional users baked into tests/data/test.sql — see tests/test_config/README.md.
    "ELN_URL": "http://127.0.0.1:3579",
    "ELN_USER": "API",
    "ELN_PASS": "1234qewR!",
    "ELN_ADMIN_USER": "ADM",
    "ELN_ADMIN_PASS": "PleaseChangeYourPassword",
    "PG_PASSWORD": "postgres",
    "PG_HOST": "localhost",
    "PG_PORT": "54320",
    "PG_USER": "postgres",
    "PG_DB": "chemotion",
    "ELN_PORT": "3579",
    "DOCKER_FILE": "compose.yml",
    "DOCKER_CWD": "../test_config",
    "DOCKER_COMPOSE_SERVICE": "eln",
    "WAIT_FOR_MANUAL_RESTART": "0",
    # Default: do NOT auto-provision a Chemotion server. Opt into the docker setup with NO_SETUP=0.
    "NO_SETUP": "1"
}

CONFIG = {}
CHEMOTION_PROCESS: subprocess.Popen | None = None


def set_config():
    global CONFIG, DEFAULT_CONFIG

    # config.json is an optional local convenience (gitignored; see config.json.sample). When absent,
    # configuration comes from environment variables, falling back to DEFAULT_CONFIG.
    file = "config.json"
    data = {}
    if os.path.exists(file):
        with open(file) as jsonfile:
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


def pytest_sessionstart(session):
    global DEFAULT_CONFIG, CONFIG, CHEMOTION_PROCESS
    set_config()
    if CONFIG.get('NO_SETUP') != '1':
        path = os.path.join(os.getcwd(), 'data/setup_chemotion_db.sh')
        path_dir = os.path.join(os.getcwd(), 'data')

        CHEMOTION_PROCESS = subprocess.Popen(path, shell=True, executable='/bin/bash', cwd=path_dir,
                                             env=dict(os.environ, **CONFIG),
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)

        while True:
            line = CHEMOTION_PROCESS.stdout.readline().decode("utf-8")
            if not line:
                raise Exception(f'{path} did not start Server')

            print(line.strip())
            if "**SUCCESS**" in line:
                Thread(target=write_proces_logs, args=()).start()
                break

        # CONFIG values are strings; the old `!= 0` compared str to int and was always true,
        # so every NO_SETUP=0 run blocked on input() (a crash under pytest's capture).
        if CONFIG["WAIT_FOR_MANUAL_RESTART"] != '0':
            print("Waiting for manual restart of the Chemotion Server...")
            input("Press Enter to continue...")

    logging.info('Config:\n' + '\n'.join([f"#\t{key}={val}" for key, val in CONFIG.items()]))


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
    from chemotion_api import Instance  # lazy: only when an integration test actually needs a server
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


# Fixtures that require a live Chemotion server/DB. Any test requesting one of these (directly or
# transitively) is auto-marked `integration` so the offline subset can run via `-m "not integration"`.
SERVER_FIXTURES = {
    "config_login", "logged_in_instance", "delete_col_prefix",
    "instance_with_collection", "instance_with_test_samples", "instance_with_test_reaction",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if SERVER_FIXTURES.intersection(getattr(item, "fixturenames", [])):
            item.add_marker(pytest.mark.integration)
