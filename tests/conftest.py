import json
import logging
import os
from threading import Thread

from psutil import process_iter, AccessDenied
from signal import SIGTERM # or SIGKILL
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
}

CONFIG = {}
CHEMOTION_PROCESS : subprocess.Popen | None = None

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
    if os.getenv('NO_SETUP') is not '1':
        path = os.path.join(os.getcwd(), 'data/setup_chemotion_db.sh')
        path_dir = os.path.join(os.getcwd(), 'data')

        CHEMOTION_PROCESS = subprocess.Popen(path, shell=True, executable='/bin/bash', cwd=path_dir,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

        while True:
            line = CHEMOTION_PROCESS.stdout.readline().decode("utf-8")
            if not line:
                raise Exception(f'{path} did not start Server')

            print(line.strip())
            if "* Listening on " in line and "3579" in line:
                Thread(target=write_proces_logs, args=()).start()
                break

    file="config.json"

    with open(file, "r") as jsonfile:
        data = json.load(jsonfile)

    for key, val in DEFAULT_CONFIG.items():
        CONFIG[key] = data.get(key, val)

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
                for conns in proc.connections(kind='inet'):
                    if conns.laddr.port == 3579:
                        proc.send_signal(SIGTERM) # or SIGKILL
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
    name =  delete_col_prefix + uuid.uuid4().__str__()
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